import secrets
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from app.api.dependencies import get_automation_settings
from app.api.email_analysis import get_analyzer_factory
from app.core.config import AutomationSettings
from app.core.tokens import create_access_token
from app.models import AuditLog, BECAlert, Email, EmailAnalysis, ExecutiveContact
from app.services.semantic_analysis import LLMErrorCode

pytestmark = pytest.mark.integration


@pytest.fixture
def automation_setup(api_app, analysis_stub, db_session, email_payload):
    key = secrets.token_urlsafe(48)
    settings = AutomationSettings(_env_file=None, automation_api_key=key)
    api_app.dependency_overrides[get_automation_settings] = lambda: settings
    api_app.dependency_overrides[get_analyzer_factory] = lambda: lambda: analysis_stub
    db_session.add(ExecutiveContact(name="Ana Pérez", position="CEO", email="ana@empresa.example"))
    db_session.commit()
    payload = {
        **email_payload,
        "sender_name": "Ana Pérez",
        "sender_email": "ana@ernpresa.example",
        "subject": "Pago urgente",
        "body_text": "Soy la directora, paga hoy. No consultes a finanzas.",
        "authentication_results": "mx; dmarc=fail",
    }
    return {"X-BEC-Automation-Key": key}, payload


@pytest.mark.parametrize(
    "kind,expected", [("valid", 201), ("invalid", 401), ("missing", 401), ("unicode", 401)]
)
def test_automation_key(api_client, automation_setup, kind, expected, caplog):
    headers, payload = automation_setup
    supplied = (
        headers
        if kind == "valid"
        else ({"X-BEC-Automation-Key": "incorrect-key"} if kind == "invalid" else {})
    )
    if kind == "unicode":
        supplied = {b"X-BEC-Automation-Key": "á".encode()}
    response = api_client.post("/api/automation/emails", json=payload, headers=supplied)
    assert response.status_code == expected
    assert headers["X-BEC-Automation-Key"] not in response.text + caplog.text


@pytest.mark.parametrize("key", ["", "short"])
def test_unconfigured_automation_is_lazy_503(api_app, api_client, email_payload, key, caplog):
    api_app.dependency_overrides[get_automation_settings] = lambda: AutomationSettings(
        _env_file=None, automation_api_key=key
    )
    assert api_client.get("/openapi.json").status_code == 200
    response = api_client.post("/api/automation/emails", json=email_payload)
    assert response.status_code == 503
    assert response.json() == {"detail": "Automation unavailable"}
    assert (
        repr(AutomationSettings(_env_file=None, automation_api_key="hidden-value")).find(
            "hidden-value"
        )
        < 0
    )


def test_ingest_idempotent_and_human_still_409(
    api_client,
    automation_setup,
    db_session,
    account,
    auth_settings,
):
    headers, payload = automation_setup
    first = api_client.post("/api/automation/emails", json=payload, headers=headers)
    assert first.status_code == 201 and first.json()["created"] is True
    second = api_client.post(
        "/api/automation/emails",
        headers=headers,
        json={**payload, "subject": "Must not replace", "body_text": "Different"},
    )
    assert second.status_code == 200 and second.json()["created"] is False
    assert second.json()["email"] == first.json()["email"]
    [audit] = list(db_session.scalars(select(AuditLog)))
    assert audit.action == "EMAIL_INGESTED"
    assert audit.actor_user_id is audit.actor_role is audit.details is None
    jwt_headers = {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}
    assert api_client.post("/api/emails", json=payload, headers=jwt_headers).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(Email)) == 1
    variant = {**payload, "message_id": payload["message_id"].lower()}
    assert (
        api_client.post("/api/automation/emails", json=variant, headers=headers).status_code == 201
    )


def test_scopes_do_not_cross(api_client, automation_setup, account, auth_settings):
    headers, payload = automation_setup
    for path in ["/api/auth/me", "/api/alerts", "/api/emails", "/api/vendors", "/api/executives"]:
        assert api_client.get(path, headers=headers).status_code == 401
    assert api_client.post("/api/emails", json=payload, headers=headers).status_code == 401
    assert api_client.post(f"/api/emails/{uuid4()}/analyze", headers=headers).status_code == 401
    jwt_headers = {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}
    assert (
        api_client.post("/api/automation/emails", json=payload, headers=jwt_headers).status_code
        == 401
    )
    assert (
        api_client.post(
            f"/api/automation/emails/{uuid4()}/analyze", headers=jwt_headers
        ).status_code
        == 401
    )


def test_automation_high_alert_idempotence_and_audit(
    api_client, automation_setup, db_session, analysis_stub
):
    headers, payload = automation_setup
    email = api_client.post("/api/automation/emails", json=payload, headers=headers).json()["email"]
    path = f"/api/automation/emails/{email['id']}/analyze"
    first = api_client.post(path, headers=headers)
    assert first.status_code == 200
    result = first.json()
    assert result["analysis"]["status"] == "COMPLETED"
    assert result["analysis"]["risk_level"] == "CRITICAL" and result["alert_id"] is not None
    assert api_client.post(path, headers=headers).json() == result
    assert analysis_stub.calls == 1
    assert db_session.scalar(select(func.count()).select_from(EmailAnalysis)) == 1
    assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 1
    events = list(db_session.scalars(select(AuditLog).order_by(AuditLog.created_at, AuditLog.id)))
    assert {e.action for e in events} == {"EMAIL_INGESTED", "EMAIL_ANALYZED", "BEC_ALERT_CREATED"}
    assert len(events) == 3
    assert all(e.actor_user_id is e.actor_role is e.details is None for e in events)


@pytest.mark.parametrize("semantic_score,level", [(0, "LOW"), (100, "MEDIUM")])
def test_automation_low_medium_have_no_alert(
    api_client, automation_setup, db_session, analysis_stub, semantic_score, level
):
    headers, payload = automation_setup
    analysis_stub.score = semantic_score
    body = {
        **payload,
        "sender_name": "Unknown Person",
        "sender_email": "person@other.example",
        "subject": "Reunión",
        "body_text": "Reunión mañana",
        "reply_to": None,
        "return_path": None,
        "authentication_results": None,
    }
    email_id = api_client.post("/api/automation/emails", json=body, headers=headers).json()[
        "email"
    ]["id"]
    response = api_client.post(f"/api/automation/emails/{email_id}/analyze", headers=headers)
    assert response.status_code == 200
    assert response.json()["analysis"]["risk_level"] == level
    assert response.json()["alert_id"] is None
    assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 0


@pytest.mark.parametrize(
    "code,http",
    [
        (LLMErrorCode.NOT_CONFIGURED, 503),
        (LLMErrorCode.TIMEOUT, 502),
        (LLMErrorCode.PROVIDER_ERROR, 502),
        (LLMErrorCode.INVALID_OUTPUT, 502),
    ],
)
def test_error_and_retry_same_analysis_one_alert(
    api_client, automation_setup, db_session, analysis_stub, code, http
):
    headers, payload = automation_setup
    email_id = api_client.post("/api/automation/emails", json=payload, headers=headers).json()[
        "email"
    ]["id"]
    path = f"/api/automation/emails/{email_id}/analyze"
    analysis_stub.failure = code
    failed = api_client.post(path, headers=headers)
    assert failed.status_code == http
    failure = failed.json()
    assert failure["alert_id"] is None and failure["analysis"]["status"] == "ERROR"
    assert failure["analysis"]["risk_level"] is failure["analysis"]["risk_score"] is None
    assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 0
    analysis_stub.failure = None
    retry = api_client.post(path, headers=headers)
    assert retry.status_code == 200
    assert retry.json()["analysis"]["id"] == failure["analysis"]["id"]
    assert retry.json()["alert_id"] is not None
    assert api_client.post(path, headers=headers).json() == retry.json()
    assert analysis_stub.calls == 2
    assert db_session.scalar(select(func.count()).select_from(EmailAnalysis)) == 1
    assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 1


def test_missing_and_invalid_requests(api_client, automation_setup):
    headers, payload = automation_setup
    assert (
        api_client.post(f"/api/automation/emails/{uuid4()}/analyze", headers=headers).status_code
        == 404
    )
    assert api_client.post("/api/automation/emails/bad/analyze", headers=headers).status_code == 400
    assert (
        api_client.post(
            "/api/automation/emails", headers=headers, json={**payload, "label": "BEC"}
        ).status_code
        == 400
    )


def test_concurrent_ingestion_uses_unique_winner(
    api_client, automation_setup, db_session, monkeypatch
):
    from app.services import email_ingestion

    headers, payload = automation_setup
    barrier = Barrier(2)
    original = email_ingestion.ingest_email

    def synchronized(*args, **kwargs):
        barrier.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(email_ingestion, "ingest_email", synchronized)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(api_client.post, "/api/automation/emails", json=payload, headers=headers)
            for _ in range(2)
        ]
        responses = [f.result(timeout=15) for f in futures]
    assert sorted(r.status_code for r in responses) == [200, 201]
    assert responses[0].json()["email"]["id"] == responses[1].json()["email"]["id"]
    assert db_session.scalar(select(func.count()).select_from(Email)) == 1
    assert list(db_session.scalars(select(AuditLog.action))) == ["EMAIL_INGESTED"]


def test_concurrent_pipeline_one_call_analysis_alert(
    api_client, automation_setup, analysis_stub, db_session
):
    headers, payload = automation_setup
    email_id = api_client.post("/api/automation/emails", json=payload, headers=headers).json()[
        "email"
    ]["id"]
    path = f"/api/automation/emails/{email_id}/analyze"
    analysis_stub.entered, analysis_stub.release = Event(), Event()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(api_client.post, path, headers=headers)
        try:
            assert analysis_stub.entered.wait(10)
            second = pool.submit(api_client.post, path, headers=headers)
        finally:
            analysis_stub.release.set()
        results = [first.result(timeout=15), second.result(timeout=15)]
    assert all(r.status_code == 200 for r in results)
    assert results[0].json() == results[1].json()
    assert analysis_stub.calls == 1
    assert db_session.scalar(select(func.count()).select_from(EmailAnalysis)) == 1
    assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 1


def test_constant_time_key_comparison(api_client, automation_setup, monkeypatch):
    from app.api import dependencies

    original = dependencies.secrets.compare_digest
    calls = []

    def compare(left, right):
        calls.append((type(left), type(right)))
        return original(left, right)

    monkeypatch.setattr(dependencies.secrets, "compare_digest", compare)
    headers, payload = automation_setup
    assert (
        api_client.post("/api/automation/emails", json=payload, headers=headers).status_code == 201
    )
    assert calls == [(bytes, bytes)]


def test_automation_alert_audit_failure_is_atomic(
    api_client,
    automation_setup,
    db_session,
    migrated_engine,
):
    headers, payload = automation_setup
    email_id = api_client.post("/api/automation/emails", json=payload, headers=headers).json()[
        "email"
    ]["id"]
    with migrated_engine.begin() as connection:
        connection.execute(
            text("""
            CREATE FUNCTION public.reject_test_automation_alert() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
                IF NEW.action = 'BEC_ALERT_CREATED' AND NEW.actor_user_id IS NULL THEN
                    RAISE EXCEPTION 'Test audit failure' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END; $$
        """)
        )
        connection.execute(
            text("""
            CREATE TRIGGER reject_test_automation_alert BEFORE INSERT ON public.audit_log
            FOR EACH ROW EXECUTE FUNCTION public.reject_test_automation_alert()
        """)
        )
    try:
        response = api_client.post(f"/api/automation/emails/{email_id}/analyze", headers=headers)
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}
        assert db_session.scalar(select(func.count()).select_from(EmailAnalysis)) == 0
        assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 0
        assert list(db_session.scalars(select(AuditLog.action))) == ["EMAIL_INGESTED"]
    finally:
        db_session.rollback()
        with migrated_engine.begin() as connection:
            connection.execute(
                text("DROP TRIGGER reject_test_automation_alert ON public.audit_log")
            )
            connection.execute(text("DROP FUNCTION public.reject_test_automation_alert()"))
