from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_auth_settings, get_current_user
from app.core.config import AuthSettings
from app.core.database import get_session
from app.core.tokens import create_access_token
from app.models import User
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse
from app.services.audit import AuditAction, AuditReason, record_security_event
from app.services.authentication import AuthenticationFailed, authenticate

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> TokenResponse:
    try:
        user = authenticate(
            session, email=str(payload.email), password=payload.password.get_secret_value()
        )
    except AuthenticationFailed as error:
        record_security_event(
            session,
            AuditAction.LOGIN_INACTIVE if error.inactive else AuditAction.LOGIN_FAILED,
            actor=error.actor,
            peer=request.client.host if request.client else None,
            reason=AuditReason.INACTIVE_USER if error.inactive else AuditReason.INVALID_CREDENTIALS,
        )
        session.commit()
        raise HTTPException(
            status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Bearer"}
        ) from None
    token = create_access_token(user.id, settings)
    record_security_event(
        session,
        AuditAction.LOGIN_SUCCEEDED,
        actor=user,
        peer=request.client.host if request.client else None,
    )
    session.commit()
    return TokenResponse(access_token=token, expires_in=settings.jwt_access_token_minutes * 60)


@router.get("/me", response_model=CurrentUserResponse)
def me(user: Annotated[User, Depends(get_current_user)]) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(user)
