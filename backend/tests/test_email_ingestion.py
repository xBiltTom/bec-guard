from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.tokens import create_access_token
from app.models import AuditLog, Email, Role, User
from app.schemas.email import EmailIngestRequest
from app.services.audit import AuditAction
from app.services.email_ingestion import ingest_email
from app.services.mime_parser import parse_email

pytestmark = pytest.mark.integration


@pytest.fixture
def email_headers(account, auth_settings):
    return {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}


def test_email_persistence_summaries_and_audit(
    api_client, email_headers, email_payload, db_session, account
):
    response = api_client.post("/api/emails", json=email_payload, headers=email_headers)
    assert response.status_code == 201
    detail = response.json()
    resource_id = UUID(detail["id"])
    stored = db_session.get(Email, resource_id)
    normalized = EmailIngestRequest(**email_payload)
    for field, expected in normalized.model_dump().items():
        assert getattr(stored, field) == expected
    assert stored.ingested_at.utcoffset() == timedelta(0)
    assert stored.received_at == datetime(2026, 10, 20, 14, 30, tzinfo=UTC)
    assert api_client.get(f"/api/emails/{resource_id}", headers=email_headers).json() == detail
    summary = api_client.get("/api/emails", headers=email_headers).json()[0]
    assert set(summary) == {
        "id",
        "message_id",
        "sender_name",
        "sender_email",
        "reply_to",
        "subject",
        "received_at",
        "ingested_at",
    }
    assert "body_text" not in summary and "body_text" in detail
    for forbidden in ["password_hash", "label", "split", "risk_score", "bec_type", "raw_mime"]:
        assert forbidden not in detail
    [event] = db_session.scalars(select(AuditLog)).all()
    assert event.action == AuditAction.EMAIL_INGESTED
    assert event.actor_user_id == account.id and event.actor_role == Role.ANALYST
    assert event.resource_type == "email" and event.resource_id == resource_id
    assert event.details is None
    assert event.created_at.utcoffset() == timedelta(0)


def test_duplicate_message_id_and_case_identity(
    api_client, email_payload, email_headers, db_session
):
    first = api_client.post("/api/emails", json=email_payload, headers=email_headers)
    assert first.status_code == 201
    response = api_client.post("/api/emails", json=email_payload, headers=email_headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "Message-ID already exists"}
    # Message-ID identity is NOT case-folded like email addresses.
    variant = {**email_payload, "message_id": email_payload["message_id"].lower()}
    assert api_client.post("/api/emails", json=variant, headers=email_headers).status_code == 201
    assert db_session.scalar(select(func.count()).select_from(Email)) == 2
    assert db_session.scalar(select(func.count()).select_from(AuditLog)) == 2


def test_database_rejects_duplicate_message_id(db_session, account, email_payload):
    normalized = EmailIngestRequest(**email_payload)
    ingest_email(db_session, normalized, actor=account)
    db_session.add(Email(**normalized.model_dump()))
    with pytest.raises(IntegrityError) as error:
        db_session.commit()
    assert error.value.orig.sqlstate == "23505"
    assert error.value.orig.diag.constraint_name == "uq_emails_message_id"
    db_session.rollback()


def test_mime_duplicate_goes_through_same_ingestion(api_client, email_headers):
    directory = Path(__file__).parent / "fixtures" / "mime"
    for name, expected in [("plain", 201), ("duplicate", 409)]:
        normalized = parse_email((directory / f"{name}.eml").read_bytes())
        response = api_client.post(
            "/api/emails", headers=email_headers, json=normalized.model_dump(mode="json")
        )
        assert response.status_code == expected


def test_pagination_order_and_missing(
    api_client, email_headers, account, email_payload, db_session
):
    for index, date in enumerate(
        ["2026-10-19T00:00:00Z", "2026-10-20T00:00:00Z", "2026-10-20T00:00:00Z"]
    ):
        ingest_email(
            db_session,
            EmailIngestRequest(
                **{
                    **email_payload,
                    "message_id": f"<page-{index}@fixtures.example>",
                    "received_at": date,
                }
            ),
            actor=account,
        )
    rows = api_client.get("/api/emails", headers=email_headers).json()
    assert rows[0]["received_at"] == rows[1]["received_at"]
    assert rows[0]["id"] < rows[1]["id"]
    assert rows[2]["received_at"] < rows[1]["received_at"]
    page = api_client.get("/api/emails?limit=1&offset=1", headers=email_headers).json()
    assert page == [rows[1]]
    assert api_client.get("/api/emails?offset=3", headers=email_headers).json() == []
    for query in ["limit=101", "limit=0", "offset=-1"]:
        assert api_client.get(f"/api/emails?{query}", headers=email_headers).status_code == 400
    assert api_client.get(f"/api/emails/{uuid4()}", headers=email_headers).status_code == 404
    assert api_client.get("/api/emails/not-a-uuid", headers=email_headers).status_code == 400


@pytest.mark.parametrize("role", list(Role))
def test_email_rbac_uses_current_database_role(
    api_client, account, db_session, email_headers, email_payload, role
):
    original = ingest_email(db_session, EmailIngestRequest(**email_payload), actor=account)
    account.role = role
    db_session.commit()
    assert api_client.get("/api/emails", headers=email_headers).status_code == 200
    assert api_client.get(f"/api/emails/{original.id}", headers=email_headers).status_code == 200
    body = {**email_payload, "message_id": "<role-1@fixtures.example>"}
    assert api_client.post("/api/emails", json=body, headers=email_headers).status_code == (
        403 if role == Role.AUDITOR else 201
    )
    account.role = Role.ANALYST if role == Role.AUDITOR else Role.AUDITOR
    db_session.commit()
    body["message_id"] = "<role-2@fixtures.example>"
    assert api_client.post("/api/emails", json=body, headers=email_headers).status_code == (
        201 if role == Role.AUDITOR else 403
    )
    account.is_active = False
    db_session.commit()
    assert api_client.get("/api/emails", headers=email_headers).status_code == 401
    assert api_client.post("/api/emails", json=body, headers=email_headers).status_code == 401


@pytest.mark.parametrize(
    "method,path",
    [("get", "/api/emails"), ("get", f"/api/emails/{uuid4()}"), ("post", "/api/emails")],
)
def test_email_authentication_required(api_client, email_payload, method, path):
    kwargs = {"json": email_payload} if method == "post" else {}
    assert getattr(api_client, method)(path, **kwargs).status_code == 401


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_no_email_edit_or_delete(api_client, email_headers, method):
    assert (
        getattr(api_client, method)(f"/api/emails/{uuid4()}", headers=email_headers).status_code
        == 405
    )


def test_invalid_requests_do_not_echo_email_contents(
    api_client, email_payload, email_headers, caplog
):
    response = api_client.post(
        "/api/emails", headers=email_headers, json={**email_payload, "label": "BEC"}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request"}
    assert email_payload["body_text"] not in response.text + caplog.text
    assert email_payload["subject"] not in response.text + caplog.text


def test_audit_failure_rolls_back_email(db_session, email_payload):
    missing_actor = User(id=uuid4(), role=Role.ADMIN)
    with pytest.raises(IntegrityError) as error:
        ingest_email(db_session, EmailIngestRequest(**email_payload), actor=missing_actor)
    assert error.value.orig.sqlstate == "23503"
    assert db_session.scalar(select(func.count()).select_from(Email)) == 0
    assert db_session.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_unknown_database_failure_is_503_and_atomic(
    api_client, migrated_engine, db_session, email_payload, email_headers, caplog
):
    with migrated_engine.begin() as connection:
        connection.execute(
            text("""
            CREATE FUNCTION public.reject_test_email_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.action = 'EMAIL_INGESTED' THEN
                    RAISE EXCEPTION 'Test audit failure' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END; $$
        """)
        )
        connection.execute(
            text("""
            CREATE TRIGGER reject_test_email_audit BEFORE INSERT ON public.audit_log
            FOR EACH ROW EXECUTE FUNCTION public.reject_test_email_audit()
        """)
        )
    try:
        response = api_client.post("/api/emails", headers=email_headers, json=email_payload)
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}
        assert db_session.scalar(select(func.count()).select_from(Email)) == 0
        assert db_session.scalar(select(func.count()).select_from(AuditLog)) == 0
        assert email_payload["subject"] not in response.text + caplog.text
    finally:
        db_session.rollback()
        with migrated_engine.begin() as connection:
            connection.execute(text("DROP TRIGGER reject_test_email_audit ON public.audit_log"))
            connection.execute(text("DROP FUNCTION public.reject_test_email_audit()"))
