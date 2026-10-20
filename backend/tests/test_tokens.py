import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import AuthSettings
from app.core.tokens import create_access_token, decode_access_token


def test_valid_token(auth_settings):
    user_id = uuid4()
    token = create_access_token(user_id, auth_settings)
    assert decode_access_token(token, auth_settings) == user_id
    claims = jwt.decode(
        token, auth_settings.jwt_secret_key.get_secret_value(), algorithms=["HS256"]
    )
    assert set(claims) == {"sub", "iat", "exp"}
    assert claims["exp"] - claims["iat"] == 1800


@pytest.mark.parametrize(
    "case",
    [
        "expired",
        "wrong_signature",
        "tampered",
        "bad_sub",
        "missing_exp",
        "future_iat",
        "none_algorithm",
    ],
)
def test_invalid_tokens(auth_settings, case):
    now = datetime.now(UTC)
    claims = {"sub": str(uuid4()), "iat": now, "exp": now + timedelta(minutes=30)}
    key = auth_settings.jwt_secret_key.get_secret_value()
    if case == "expired":
        claims.update(iat=now - timedelta(hours=2), exp=now - timedelta(hours=1))
    elif case == "bad_sub":
        claims["sub"] = "not-a-uuid"
    elif case == "missing_exp":
        del claims["exp"]
    elif case == "future_iat":
        claims["iat"] = now + timedelta(minutes=10)
    token = jwt.encode(
        claims, secrets.token_urlsafe(48) if case == "wrong_signature" else key, algorithm="HS256"
    )
    if case == "tampered":
        header, payload, signature = token.split(".")
        token = f"{header}.{payload[:-2]}AA.{signature}"
    elif case == "none_algorithm":
        token = jwt.encode(claims, key="", algorithm="none")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token, auth_settings)


def test_secret_is_required_and_not_reflected(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        AuthSettings(_env_file=None)
    with pytest.raises(ValidationError) as error:
        AuthSettings(_env_file=None, jwt_secret_key="short-secret")
    assert "short-secret" not in str(error.value)
