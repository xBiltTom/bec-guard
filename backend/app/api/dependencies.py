import secrets
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import AuthSettings, AutomationSettings
from app.core.database import get_session
from app.core.tokens import decode_access_token
from app.models import Role, User
from app.services.audit import AuditAction, AuditReason, record_security_event

bearer = HTTPBearer(auto_error=False)
automation_header = APIKeyHeader(name="X-BEC-Automation-Key", auto_error=False)


def get_automation_settings() -> AutomationSettings:
    try:
        return AutomationSettings()
    except ValidationError:
        raise HTTPException(503, "Automation unavailable") from None


def require_automation_key(
    key: Annotated[str | None, Depends(automation_header)],
    settings: Annotated[AutomationSettings, Depends(get_automation_settings)],
) -> None:
    expected = settings.automation_api_key.get_secret_value()
    if len(expected) < 32:
        raise HTTPException(503, "Automation unavailable")
    if not secrets.compare_digest((key or "").encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(401, "Invalid automation credentials")


def get_auth_settings(request: Request) -> AuthSettings:
    return request.app.state.auth_settings


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> User:
    if credentials is None:
        raise unauthorized()
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except jwt.InvalidTokenError:
        raise unauthorized() from None
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized()
    return user


def require_roles(*roles: Role):
    if not roles:
        raise ValueError("At least one allowed role is required")

    def authorize(
        user: Annotated[User, Depends(get_current_user)],
        session: Annotated[Session, Depends(get_session)],
        request: Request,
    ) -> User:
        if user.role not in roles:
            record_security_event(
                session,
                AuditAction.RBAC_DENIED,
                actor=user,
                peer=request.client.host if request.client else None,
                reason=AuditReason.ROLE_NOT_ALLOWED,
            )
            session.commit()
            raise HTTPException(status_code=403, detail="Forbidden")
        return user

    return authorize
