from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.api.email_analysis import get_analyzer_factory
from app.core.config import LLMSettings
from app.core.database import create_session_factory
from app.core.tokens import create_access_token
from app.models import AuditLog, BECAlert, Email, EmailAnalysis, ExecutiveContact, Role, User
from app.schemas.analysis import SemanticAssessment
from app.schemas.email import EmailIngestRequest
from app.services.email_analysis import analyze_email, create_semantic_analyzer
from app.services.email_ingestion import ingest_email
from app.services.semantic_analysis import LLMErrorCode, SemanticAnalysisError

pytestmark = pytest.mark.integration


class StubAnalyzer:
    settings = LLMSettings(_env_file=None, llm_provider="openai", llm_model="fake-model")

    def __init__(self):
        self.calls = 0
        self.failure = None
        self.score = 90
        self.entered = self.release = None

    def assess(self, email, deterministic, context):
        self.calls += 1
        if self.entered:
            self.entered.set()
            assert self.release.wait(10), "Concurrent test did not release fake provider"
        if self.failure:
            raise SemanticAnalysisError(self.failure)
        return SemanticAssessment(
            risk_score=self.score,
            bec_type="EXECUTIVE_IMPERSONATION",
            signals=[
                {
                    "code": "BYPASS_APPROVAL",
                    "description": "Se pide omitir la validación.",
                    "source": "SEMANTIC",
                }
            ],
            summary="Solicitud sospechosa de suplantación ejecutiva.",
            recommended_action="Verificar por teléfono conocido antes de realizar el pago.",
        )


@pytest.fixture
def analysis_setup(api_app, db_session, account, auth_settings, email_payload):
    db_session.add(ExecutiveContact(name="Ana Pérez", position="CEO", email="ana@empresa.example"))
    db_session.commit()
    email = ingest_email(
        db_session,
        EmailIngestRequest(
            **{
                **email_payload,
                "sender_name": "Ana Pérez",
                "sender_email": "ana@ernpresa.example",
                "reply_to": "private@outside.example",
                "subject": "Pago urgente",
                "body_text": "Soy la directora. Paga hoy. No consultes con finanzas.",
                "authentication_results": "mx; dmarc=fail",
            }
        ),
        actor=account,
    )
    fake = StubAnalyzer()
    api_app.dependency_overrides[get_analyzer_factory] = lambda: lambda: fake
    headers = {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}
    return email, fake, headers


def test_completed_analysis_persisted_idempotent_and_audited(
    api_client,
    analysis_setup,
    db_session,
    account,
    caplog,
):
    email, fake, headers = analysis_setup
    response = api_client.post(
        f"/api/emails/{email.id}/analyze", headers={**headers, "X-Forwarded-For": "198.51.100.10"}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "COMPLETED"
    assert result["deterministic_score"] == 100
    assert result["semantic_score"] == 90
    assert result["risk_score"] == 95 and result["risk_level"] == "CRITICAL"
    assert result["bec_type"] == "EXECUTIVE_IMPERSONATION"
    assert result["provider"] == "openai" and result["model"] == "fake-model"
    assert result["policy_version"] == "det-v1/semantic-v1/hybrid-v1"
    assert {s["source"] for s in result["signals"]} == {"RULE", "CONTEXT", "SEMANTIC"}
    assert all(s["contribution"] == 0 for s in result["signals"] if s["source"] == "SEMANTIC")
    stored = db_session.get(EmailAnalysis, UUID(result["id"]))
    assert stored.analyzed_at.utcoffset() == timedelta(0)
    assert stored.risk_score == 95
    assert api_client.get(f"/api/emails/{email.id}/analysis", headers=headers).json() == result
    assert api_client.post(f"/api/emails/{email.id}/analyze", headers=headers).json() == result
    assert fake.calls == 1
    [event] = db_session.scalars(select(AuditLog).where(AuditLog.action == "EMAIL_ANALYZED")).all()
    assert event.actor_user_id == account.id and event.actor_role == Role.ANALYST
    assert event.resource_type == "email_analysis" and event.resource_id == stored.id
    assert event.details is None and event.ip_address != "198.51.100.10"
    events = list(db_session.scalars(select(AuditLog)))
    assert {e.action for e in events} == {"EMAIL_INGESTED", "EMAIL_ANALYZED", "BEC_ALERT_CREATED"}
    assert all(e.actor_user_id == account.id and e.actor_role == Role.ANALYST for e in events)
    assert not any(
        value in repr(event.details) + caplog.text for value in [email.subject, email.body_text]
    )


@pytest.mark.parametrize(
    "code,http_status",
    [
        (LLMErrorCode.NOT_CONFIGURED, 503),
        (LLMErrorCode.TIMEOUT, 502),
        (LLMErrorCode.PROVIDER_ERROR, 502),
        (LLMErrorCode.INVALID_OUTPUT, 502),
    ],
)
def test_error_is_not_low_and_retry_updates_same_row(
    api_client,
    analysis_setup,
    db_session,
    code,
    http_status,
):
    email, fake, headers = analysis_setup
    fake.failure = code
    response = api_client.post(f"/api/emails/{email.id}/analyze", headers=headers)
    assert response.status_code == http_status
    result = response.json()
    assert result["status"] == "ERROR" and result["error_code"] == code
    for field in [
        "risk_score",
        "risk_level",
        "bec_type",
        "semantic_score",
        "summary",
        "recommended_action",
    ]:
        assert result[field] is None
    assert result["deterministic_score"] == 100
    assert all(s["source"] in {"RULE", "CONTEXT"} for s in result["signals"])
    assert api_client.get(f"/api/emails/{email.id}/analysis", headers=headers).json() == result
    fake.failure = None
    retry = api_client.post(f"/api/emails/{email.id}/analyze", headers=headers)
    assert retry.status_code == 200 and retry.json()["status"] == "COMPLETED"
    assert retry.json()["id"] == result["id"]
    assert retry.json()["error_code"] is None
    assert fake.calls == 2
    assert db_session.scalar(select(func.count()).select_from(EmailAnalysis)) == 1
    assert set(db_session.scalars(select(AuditLog.action))) == {
        "EMAIL_INGESTED",
        "EMAIL_ANALYSIS_FAILED",
        "EMAIL_ANALYZED",
        "BEC_ALERT_CREATED",
    }


def test_real_missing_config_and_invalid_config_are_persisted(
    api_app,
    api_client,
    analysis_setup,
    monkeypatch,
):
    email, _, headers = analysis_setup

    def missing():
        from app.services.semantic_analysis import SemanticAnalyzer

        return SemanticAnalyzer(LLMSettings(_env_file=None))

    api_app.dependency_overrides[get_analyzer_factory] = lambda: missing
    assert api_client.post(f"/api/emails/{email.id}/analyze", headers=headers).status_code == 503
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "invalid-value")
    api_app.dependency_overrides[get_analyzer_factory] = lambda: create_semantic_analyzer
    response = api_client.post(f"/api/emails/{email.id}/analyze", headers=headers)
    assert response.status_code == 503
    assert response.json()["error_code"] == "LLM_NOT_CONFIGURED"
    assert "invalid-value" not in response.text


@pytest.mark.parametrize("role", list(Role))
def test_rbac_current_role_and_activity(api_client, analysis_setup, db_session, account, role):
    email, fake, headers = analysis_setup
    account.role = role
    db_session.commit()
    response = api_client.post(f"/api/emails/{email.id}/analyze", headers=headers)
    assert response.status_code == (403 if role == Role.AUDITOR else 200)
    assert api_client.get(f"/api/emails/{email.id}/analysis", headers=headers).status_code == (
        404 if role == Role.AUDITOR else 200
    )
    account.role = Role.ANALYST if role == Role.AUDITOR else Role.AUDITOR
    db_session.commit()
    assert api_client.post(f"/api/emails/{email.id}/analyze", headers=headers).status_code == (
        200 if role == Role.AUDITOR else 403
    )
    account.role = Role.AUDITOR
    db_session.commit()
    assert api_client.get(f"/api/emails/{email.id}/analysis", headers=headers).status_code == 200
    assert fake.calls == 1
    account.is_active = False
    db_session.commit()
    for suffix, method in [("analyze", api_client.post), ("analysis", api_client.get)]:
        assert method(f"/api/emails/{email.id}/{suffix}", headers=headers).status_code == 401


def test_missing_email_analysis_auth_and_completed_without_configuration(
    api_app,
    api_client,
    analysis_setup,
):
    email, fake, headers = analysis_setup
    for suffix, method in [("analyze", api_client.post), ("analysis", api_client.get)]:
        assert method(f"/api/emails/{email.id}/{suffix}").status_code == 401
        assert method(f"/api/emails/{uuid4()}/{suffix}", headers=headers).status_code == 404
        assert method(f"/api/emails/invalid/{suffix}", headers=headers).status_code == 400
    assert api_client.get(f"/api/emails/{email.id}/analysis", headers=headers).status_code == 404
    assert fake.calls == 0
    assert api_client.post(f"/api/emails/{email.id}/analyze", headers=headers).status_code == 200

    def forbidden_factory():
        raise AssertionError("Completed analysis must not initialize provider")

    api_app.dependency_overrides[get_analyzer_factory] = lambda: forbidden_factory
    assert api_client.post(f"/api/emails/{email.id}/analyze", headers=headers).status_code == 200


def test_audit_failure_rolls_back_analysis_and_retry(
    api_client,
    analysis_setup,
    migrated_engine,
    db_session,
):
    email, fake, headers = analysis_setup
    with migrated_engine.begin() as connection:
        connection.execute(
            text("""
            CREATE FUNCTION public.reject_test_analysis_audit()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.action IN ('EMAIL_ANALYZED', 'EMAIL_ANALYSIS_FAILED') THEN
                    RAISE EXCEPTION 'Test audit failure' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END; $$
        """)
        )
        connection.execute(
            text("""
            CREATE TRIGGER reject_test_analysis_audit BEFORE INSERT ON public.audit_log
            FOR EACH ROW EXECUTE FUNCTION public.reject_test_analysis_audit()
        """)
        )
    try:
        assert (
            api_client.post(f"/api/emails/{email.id}/analyze", headers=headers).status_code == 503
        )
        assert db_session.scalar(select(func.count()).select_from(EmailAnalysis)) == 0
        fake.failure = LLMErrorCode.TIMEOUT
        assert (
            api_client.post(f"/api/emails/{email.id}/analyze", headers=headers).status_code == 503
        )
        assert db_session.scalar(select(func.count()).select_from(EmailAnalysis)) == 0
        assert list(db_session.scalars(select(AuditLog.action))) == ["EMAIL_INGESTED"]
    finally:
        db_session.rollback()
        with migrated_engine.begin() as connection:
            connection.execute(text("DROP TRIGGER reject_test_analysis_audit ON public.audit_log"))
            connection.execute(text("DROP FUNCTION public.reject_test_analysis_audit()"))


def test_low_result_has_no_bec_type(api_client, analysis_setup, db_session):
    email, fake, headers = analysis_setup
    db_session.query(ExecutiveContact).delete()
    stored = db_session.get(Email, email.id)
    stored.sender_name, stored.sender_email = "Unknown Person", "person@other.example"
    stored.reply_to = stored.return_path = stored.authentication_results = None
    stored.subject, stored.body_text = "Reunión urgente", "Reunión mañana."
    db_session.commit()
    fake.score = 5
    result = api_client.post(f"/api/emails/{email.id}/analyze", headers=headers).json()
    assert result["status"] == "COMPLETED" and result["risk_level"] == "LOW"
    assert result["bec_type"] is None
    assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 0


def test_concurrent_analysis_spends_once(analysis_setup, migrated_engine, account):
    email, fake, _ = analysis_setup
    fake.entered, fake.release = Event(), Event()
    second_started = Event()
    actor_id = account.id

    def run(second=False):
        with create_session_factory(migrated_engine)() as session:
            actor = session.get(User, actor_id)
            if second:
                second_started.set()
            return analyze_email(session, email.id, actor=actor, analyzer_factory=lambda: fake).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run)
        try:
            assert fake.entered.wait(10)
            second = pool.submit(run, True)
            assert second_started.wait(10)
        finally:
            fake.release.set()
        assert first.result(timeout=10) == second.result(timeout=10)
    assert fake.calls == 1
    with create_session_factory(migrated_engine)() as session:
        assert session.scalar(select(func.count()).select_from(EmailAnalysis)) == 1
        assert session.scalar(select(func.count()).select_from(BECAlert)) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("deterministic_score", 101),
        ("semantic_score", -1),
        ("risk_score", 101),
        ("risk_level", "INVALID"),
        ("status", "PENDING"),
        ("bec_type", "LEGITIMATE"),
        ("risk_level", "LOW"),
        ("status", "ERROR"),
        ("error_code", "RAW_ERROR"),
    ],
)
def test_database_result_constraints(api_client, analysis_setup, db_session, field, value):
    email, _, headers = analysis_setup
    assert api_client.post(f"/api/emails/{email.id}/analyze", headers=headers).status_code == 200
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(f"UPDATE public.email_analysis SET {field} = :value"), {"value": value}
        )
        db_session.commit()
    db_session.rollback()


def test_unique_email_and_foreign_key(api_client, analysis_setup, db_session):
    email, _, headers = analysis_setup
    result = api_client.post(f"/api/emails/{email.id}/analyze", headers=headers).json()
    row = db_session.get(EmailAnalysis, UUID(result["id"]))
    fields = {column.name: getattr(row, column.name) for column in EmailAnalysis.__table__.columns}
    fields["id"] = uuid4()
    db_session.add(EmailAnalysis(**fields))
    with pytest.raises(IntegrityError) as error:
        db_session.commit()
    assert error.value.orig.diag.constraint_name == "uq_email_analysis_email_id"
    db_session.rollback()
    fields["id"], fields["email_id"] = uuid4(), uuid4()
    db_session.add(EmailAnalysis(**fields))
    with pytest.raises(IntegrityError) as error:
        db_session.commit()
    assert error.value.orig.sqlstate == "23503"
    db_session.rollback()


def test_api_through_langchain_structured_boundary(api_app, api_client, analysis_setup):
    from langchain_core.runnables import RunnableLambda

    from app.services.semantic_analysis import SemanticAnalyzer

    email, stub, headers = analysis_setup
    messages_seen = []

    class Chat:
        def with_structured_output(self, schema, *, method):
            assert schema is SemanticAssessment and method == "json_schema"

            def invoke(messages):
                messages_seen.extend(messages)
                return stub.assess(None, None, None).model_dump()

            return RunnableLambda(invoke)

    api_app.dependency_overrides[get_analyzer_factory] = lambda: (
        lambda: SemanticAnalyzer(stub.settings, lambda _: Chat())
    )
    response = api_client.post(f"/api/emails/{email.id}/analyze", headers=headers)
    assert response.status_code == 200
    assert response.json()["risk_score"] == 95
    assert len(messages_seen) == 2 and "UNTRUSTED" in messages_seen[0].content
    assert stub.calls == 1


def test_retry_audit_failure_preserves_previous_error(api_client, analysis_setup, db_session):
    email, fake, headers = analysis_setup
    fake.failure = LLMErrorCode.TIMEOUT
    previous = api_client.post(f"/api/emails/{email.id}/analyze", headers=headers).json()
    fake.failure = None
    with pytest.raises(IntegrityError):
        analyze_email(
            db_session,
            email.id,
            actor=User(id=uuid4(), role=Role.ADMIN),
            analyzer_factory=lambda: fake,
        )
    current = api_client.get(f"/api/emails/{email.id}/analysis", headers=headers).json()
    assert current == previous
