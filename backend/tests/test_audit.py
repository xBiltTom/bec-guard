import json
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import AuditLog, Role
from app.services.admin import create_initial_admin
from app.services.audit import AuditAction, AuditReason, record_security_event

pytestmark = pytest.mark.integration
PASSWORD = "a long test password"


def events(session):
    return session.scalars(select(AuditLog).order_by(AuditLog.created_at)).all()


def test_bootstrap_event_is_atomic_and_contains_snapshot(db_session):
    admin = create_initial_admin(
        db_session, name="Admin", email="admin@example.com", password=PASSWORD
    )
    [event] = events(db_session)
    assert event.action == AuditAction.ADMIN_BOOTSTRAPPED
    assert event.actor_user_id == admin.id
    assert event.actor_role is Role.ADMIN
    assert event.resource_id == admin.id
    assert event.details is None
    assert isinstance(event.id, UUID)
    assert event.created_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("case", ["success", "wrong_password", "unknown", "inactive"])
def test_login_audit_without_secrets(api_client, account, db_session, case):
    if case == "inactive":
        account.is_active = False
        db_session.commit()
    response = api_client.post(
        "/api/auth/login",
        json={
            "email": "missing@example.com" if case == "unknown" else account.email,
            "password": "wrong password" if case == "wrong_password" else PASSWORD,
        },
    )
    assert response.status_code == (200 if case == "success" else 401)
    [event] = events(db_session)
    expected = {
        "success": AuditAction.LOGIN_SUCCEEDED,
        "wrong_password": AuditAction.LOGIN_FAILED,
        "unknown": AuditAction.LOGIN_FAILED,
        "inactive": AuditAction.LOGIN_INACTIVE,
    }
    assert event.action == expected[case]
    assert event.actor_user_id == (None if case == "unknown" else account.id)
    assert event.actor_role == (None if case == "unknown" else Role.ANALYST)
    stored = json.dumps(event.details)
    assert PASSWORD not in stored
    assert account.password_hash not in stored
    assert not any(key in stored.lower() for key in ["password", "hash", "token", "secret"])
    if case == "success":
        token = response.json()["access_token"]
        assert token not in stored
        assert (
            api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code
            == 200
        )
        assert len(events(db_session)) == 1  # No audit spam for successful /me.


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_database_rejects_audit_mutations(db_session, operation):
    event = record_security_event(
        db_session,
        AuditAction.LOGIN_FAILED,
        reason=AuditReason.INVALID_CREDENTIALS,
        peer="127.0.0.1",
    )
    db_session.commit()
    assert event.ip_address == "127.0.0.1"
    statement = (
        "UPDATE public.audit_log SET details = '{}'::jsonb WHERE id = :id"
        if operation == "UPDATE"
        else "DELETE FROM public.audit_log WHERE id = :id"
    )
    with pytest.raises(DBAPIError) as error:
        db_session.execute(text(statement), {"id": event.id})
    assert error.value.orig.sqlstate == "55000"
    db_session.rollback()
    assert db_session.get(AuditLog, event.id) is not None


def test_arbitrary_audit_metadata_is_rejected(db_session):
    with pytest.raises(ValueError, match="predefined"):
        record_security_event(db_session, AuditAction.LOGIN_FAILED, reason="password: sensitive")
