from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.core.config import AuthSettings


def create_access_token(user_id: UUID, settings: AuthSettings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.jwt_access_token_minutes),
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str, settings: AuthSettings) -> UUID:
    claims = jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "iat", "exp"]},
    )
    if type(claims["iat"]) is not int or type(claims["exp"]) is not int:
        raise jwt.InvalidTokenError("Invalid timestamps")
    if claims["exp"] <= claims["iat"]:
        raise jwt.InvalidTokenError("Invalid expiration")
    try:
        return UUID(claims["sub"])
    except ValueError, TypeError, AttributeError:
        raise jwt.InvalidTokenError("Invalid subject") from None
