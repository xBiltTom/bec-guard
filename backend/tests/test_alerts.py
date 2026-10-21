from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.api.email_analysis import get_analyzer_factory
from app.core.tokens import create_access_token
from app.models import AuditLog, BECAlert, EmailAnalysis, Role
from app.schemas.email import EmailIngestRequest
from app.services.alerts import ensure_alert_for_analysis
from app.services.email_ingestion import ingest_email
from app.services.hybrid_scoring import risk_level

pytestmark = pytest.mark.integration


@pytest.fixture
def alert_setup(db_session, account, email_payload, auth_settings, api_app, analysis_stub):
    email = ingest_email(db_session, EmailIngestRequest(**email_payload), actor=account)
    api_app.dependency_overrides[get_analyzer_factory] = lambda: lambda: analysis_stub
    headers = {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}

    def assessment(score=70, status="COMPLETED"):
        row = EmailAnalysis(
            email_id=email.id,
            status=status,
            deterministic_score=100,
            semantic_score=score if status == "COMPLETED" else None,
            risk_score=score if status == "COMPLETED" else None,
            risk_level=risk_level(score) if status == "COMPLETED" else None,
            bec_type=None,
            signals=[],
            summary="Test" if status == "COMPLETED" else None,
            recommended_action="Verify" if status == "COMPLETED" else None,
            provider="openai",
            model="unit-test-model",
            policy_version="det-v1/semantic-v1/hybrid-v1",
            error_code="LLM_TIMEOUT" if status == "ERROR" else None,
            analyzed_at=datetime.now(UTC),
        )
        db_session.add(row)
        db_session.commit()
        return row

    return email, assessment, headers


@pytest.mark.parametrize(
    "score,status,expected",
    [
        (0, "COMPLETED", False),
        (39, "COMPLETED", False),
        (40, "COMPLETED", False),
        (69, "COMPLETED", False),
        (70, "COMPLETED", True),
        (84, "COMPLETED", True),
        (85, "COMPLETED", True),
        (100, "COMPLETED", True),
        (100, "ERROR", False),
    ],
)
def test_alert_policy_and_idempotence(db_session, account, alert_setup, score, status, expected):
    _, assessment, _ = alert_setup
    row = assessment(score, status)
    alert = ensure_alert_for_analysis(db_session, row, actor=account, peer="127.0.0.1")
    db_session.commit()
    assert (alert is not None) is expected
    again = ensure_alert_for_analysis(db_session, row, actor=account)
    db_session.commit()
    assert (again.id if again else None) == (alert.id if alert else None)
    assert db_session.scalar(select(func.count()).select_from(BECAlert)) == int(expected)
    events = list(
        db_session.scalars(select(AuditLog).where(AuditLog.action == "BEC_ALERT_CREATED"))
    )
    assert len(events) == int(expected)
    if expected:
        assert alert.status == "OPEN" and alert.verdict is None
        assert alert.assigned_to is alert.resolution is alert.closed_at is None
        assert alert.created_at.utcoffset().total_seconds() == 0
        event = events[0]
        assert event.actor_user_id == account.id and event.actor_role == Role.ANALYST
        assert event.resource_type == "bec_alert" and event.resource_id == alert.id
        assert event.ip_address == "127.0.0.1" and event.details is None


def test_completed_from_phase5_recovers_alert_without_llm(api_client, alert_setup, analysis_stub):
    email, assessment, headers = alert_setup
    old = assessment(85)
    first = api_client.post(f"/api/emails/{email.id}/analyze", headers=headers)
    assert first.status_code == 200 and first.json()["id"] == str(old.id)
    rows = api_client.get("/api/alerts", headers=headers).json()
    assert len(rows) == 1
    assert (
        api_client.post(f"/api/emails/{email.id}/analyze", headers=headers).json() == first.json()
    )
    assert api_client.get("/api/alerts", headers=headers).json() == rows
    assert analysis_stub.calls == 0


@pytest.mark.parametrize("role", list(Role))
def test_alert_reads_and_no_hitl(api_client, db_session, account, alert_setup, role):
    email, assessment, headers = alert_setup
    row = assessment()
    alert = ensure_alert_for_analysis(db_session, row, actor=account)
    account.role = role
    db_session.commit()
    response = api_client.get("/api/alerts", headers=headers)
    assert response.status_code == 200
    [summary] = response.json()
    assert summary["email_id"] == str(email.id) and summary["risk_score"] == 70
    assert summary["sender_email"] == email.sender_email and summary["subject"] == email.subject
    assert "body_text" not in summary and "signals" not in summary
    detail = api_client.get(f"/api/alerts/{alert.id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["analysis"]["id"] == str(row.id)
    assert "body_text" not in detail.text
    for method in [api_client.patch, api_client.delete, api_client.post]:
        assert method(f"/api/alerts/{alert.id}", headers=headers).status_code == 405
    assert api_client.get("/api/alerts").status_code == 401
    assert api_client.get(f"/api/alerts/{alert.id}").status_code == 401
    assert api_client.get(f"/api/alerts/{uuid4()}", headers=headers).status_code == 404
    assert api_client.get("/api/alerts/invalid", headers=headers).status_code == 400
    account.is_active = False
    db_session.commit()
    assert api_client.get("/api/alerts", headers=headers).status_code == 401


def test_alert_pagination(api_client, db_session, account, alert_setup, email_payload):
    _, assessment, headers = alert_setup
    first = ensure_alert_for_analysis(db_session, assessment(), actor=account)
    db_session.commit()
    # An additional Email and valid assessment, with identical alert timestamps.
    email = ingest_email(
        db_session,
        EmailIngestRequest(**{**email_payload, "message_id": "<page-alert@fixtures.example>"}),
        actor=account,
    )
    row = db_session.get(EmailAnalysis, first.analysis_id)
    fields = {c.name: getattr(row, c.name) for c in EmailAnalysis.__table__.columns}
    fields.update(id=uuid4(), email_id=email.id)
    second_analysis = EmailAnalysis(**fields)
    db_session.add(second_analysis)
    second = ensure_alert_for_analysis(db_session, second_analysis, actor=account)
    second.created_at = first.created_at
    db_session.commit()
    rows = api_client.get("/api/alerts", headers=headers).json()
    assert [r["id"] for r in rows] == sorted([str(first.id), str(second.id)])
    assert api_client.get("/api/alerts?limit=1&offset=1", headers=headers).json() == rows[1:]
    for query in ["limit=0", "limit=101", "offset=-1"]:
        assert api_client.get(f"/api/alerts?{query}", headers=headers).status_code == 400


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "INVALID"),
        ("verdict", "PENDING"),
        ("closed_at", datetime.now(UTC)),
        ("assigned_to", uuid4()),
        ("analysis_id", uuid4()),
    ],
)
def test_alert_database_constraints(db_session, account, alert_setup, field, value):
    _, assessment, _ = alert_setup
    alert = ensure_alert_for_analysis(db_session, assessment(), actor=account)
    db_session.commit()
    with pytest.raises(IntegrityError):
        db_session.execute(text(f"UPDATE public.bec_alerts SET {field} = :value"), {"value": value})
        db_session.commit()
    db_session.rollback()
    duplicate = BECAlert(analysis_id=alert.analysis_id)
    db_session.add(duplicate)
    with pytest.raises(IntegrityError) as error:
        db_session.commit()
    assert error.value.orig.diag.constraint_name == "uq_bec_alerts_analysis_id"
    db_session.rollback()


def test_alert_audit_failure_rolls_back_entire_pipeline(
    api_client,
    alert_setup,
    db_session,
    migrated_engine,
):
    email, _, headers = alert_setup
    # Force high local evidence without changing scoring or invoking an LLM.
    from app.models import ExecutiveContact

    db_session.add(
        ExecutiveContact(name="Nora Prisma", position="CEO", email="nora@official.example")
    )
    email.sender_email = "nora@officia1.example"
    db_session.commit()
    with migrated_engine.begin() as conn:
        conn.execute(
            text("""
            CREATE FUNCTION public.reject_test_alert_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.action = 'BEC_ALERT_CREATED' THEN
                    RAISE EXCEPTION 'Test failure' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END; $$
        """)
        )
        conn.execute(
            text("""
            CREATE TRIGGER reject_test_alert_audit BEFORE INSERT ON public.audit_log
            FOR EACH ROW EXECUTE FUNCTION public.reject_test_alert_audit()
        """)
        )
    try:
        response = api_client.post(f"/api/emails/{email.id}/analyze", headers=headers)
        assert response.status_code == 503
        assert db_session.scalar(select(func.count()).select_from(EmailAnalysis)) == 0
        assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 0
        assert list(db_session.scalars(select(AuditLog.action))) == ["EMAIL_INGESTED"]
    finally:
        db_session.rollback()
        with migrated_engine.begin() as conn:
            conn.execute(text("DROP TRIGGER reject_test_alert_audit ON public.audit_log"))
            conn.execute(text("DROP FUNCTION public.reject_test_alert_audit()"))
