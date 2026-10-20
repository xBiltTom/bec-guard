from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.dependencies import require_roles
from app.core.tokens import create_access_token
from app.models import AuditLog, Role, User
from app.services.audit import AuditAction

pytestmark = pytest.mark.integration


@pytest.fixture
def protected_client(api_app):
    # This route exists only in the test app, never in the production router.
    @api_app.get("/test/protected")
    def protected(user: Annotated[User, Depends(require_roles(Role.ADMIN, Role.MANAGER))]):
        return {"role": user.role}

    with TestClient(api_app) as client:
        yield client


@pytest.mark.parametrize("role", [Role.ADMIN, Role.MANAGER])
def test_permitted_role(protected_client, account, db_session, auth_settings, role):
    account.role = role
    db_session.commit()
    token = create_access_token(account.id, auth_settings)
    response = protected_client.get("/test/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"role": role.value}


def test_forbidden_role(protected_client, account, auth_settings, db_session):
    token = create_access_token(account.id, auth_settings)
    response = protected_client.get("/test/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    event = db_session.scalar(select(AuditLog))
    assert event.action == AuditAction.RBAC_DENIED
    assert event.actor_role is Role.ANALYST


def test_role_change_uses_database_without_new_token(
    protected_client, account, db_session, auth_settings
):
    token = create_access_token(account.id, auth_settings)
    headers = {"Authorization": f"Bearer {token}"}
    assert protected_client.get("/test/protected", headers=headers).status_code == 403
    account.role = Role.MANAGER
    db_session.commit()
    assert protected_client.get("/test/protected", headers=headers).status_code == 200
    account.role = Role.ANALYST
    db_session.commit()
    assert protected_client.get("/test/protected", headers=headers).status_code == 403


def test_inactive_user_is_unauthenticated(protected_client, account, db_session, auth_settings):
    token = create_access_token(account.id, auth_settings)
    account.is_active = False
    db_session.commit()
    response = protected_client.get("/test/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_missing_token_is_unauthenticated(protected_client):
    assert protected_client.get("/test/protected").status_code == 401


def test_role_claim_does_not_override_database(protected_client, account, auth_settings):
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": str(account.id), "iat": now, "exp": now + timedelta(minutes=30), "role": "ADMIN"},
        auth_settings.jwt_secret_key.get_secret_value(),
        algorithm="HS256",
    )
    assert (
        protected_client.get(
            "/test/protected", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 403
    )
