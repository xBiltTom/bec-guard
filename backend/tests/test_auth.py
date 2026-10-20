from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.passwords import verify_password
from app.core.tokens import create_access_token

pytestmark = pytest.mark.integration
PASSWORD = "a long test password"


def login(client, email="analyst@example.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_login_and_me(api_client, account):
    response = login(api_client, "  Analyst@EXAMPLE.COM ")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in"}
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 1800
    assert account.password_hash not in response.text
    me = api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert set(me.json()) == {"id", "name", "email", "role", "is_active", "created_at"}
    assert me.json()["id"] == str(account.id)
    assert "password" not in me.text


@pytest.mark.parametrize("case", ["wrong_password", "missing_email", "inactive"])
def test_login_failures_are_generic(api_client, account, db_session, case):
    if case == "inactive":
        account.is_active = False
        db_session.commit()
    response = login(
        api_client,
        "missing@example.com" if case == "missing_email" else account.email,
        "wrong password" if case == "wrong_password" else PASSWORD,
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_requires_token(api_client):
    assert api_client.get("/api/auth/me").status_code == 401


def test_disabled_after_issuing_token(api_client, account, db_session, auth_settings):
    token = create_access_token(account.id, auth_settings)
    account.is_active = False
    db_session.commit()
    response = api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "case", ["expired", "wrong_signature", "invalid_sub", "unknown_sub", "tampered"]
)
def test_me_rejects_invalid_tokens(api_client, account, auth_settings, case):
    now = datetime.now(UTC)
    claims = {"sub": str(account.id), "iat": now, "exp": now + timedelta(minutes=30)}
    if case == "expired":
        claims.update(iat=now - timedelta(hours=2), exp=now - timedelta(hours=1))
    if case == "invalid_sub":
        claims["sub"] = "bad"
    if case == "unknown_sub":
        claims["sub"] = str(uuid4())
    token = jwt.encode(
        claims,
        "x" * 48 if case == "wrong_signature" else auth_settings.jwt_secret_key.get_secret_value(),
        algorithm="HS256",
    )
    if case == "tampered":
        header, payload, signature = token.split(".")
        token = f"{header}.{payload[:-2]}AA.{signature}"
    response = api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_validation_never_reflects_password(api_client):
    secret = "private-input-marker" * 20
    response = api_client.post("/api/auth/login", json={"email": "invalid", "password": secret})
    assert response.status_code == 400
    assert secret not in response.text
    assert response.json() == {"detail": "Invalid request"}


def test_login_rehashes_old_parameters(api_client, account, db_session):
    previous = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8192, parallelism=1),)).hash(
        PASSWORD
    )
    account.password_hash = previous
    db_session.commit()
    assert login(api_client).status_code == 200
    db_session.refresh(account)
    assert account.password_hash != previous
    assert verify_password(PASSWORD, account.password_hash)


def test_unknown_identity_performs_dummy_verification(api_client, monkeypatch):
    from app.services import authentication

    original = authentication.verify_and_rehash
    seen = []

    def traced_verify(password, stored_hash):
        seen.append(stored_hash)
        return original(password, stored_hash)

    monkeypatch.setattr(authentication, "verify_and_rehash", traced_verify)
    assert login(api_client, email="missing@example.com").status_code == 401
    assert seen == [authentication.dummy_hash]


def test_password_hash_and_token_are_absent_from_logs(api_client, account, caplog):
    response = login(api_client)
    assert response.status_code == 200
    assert PASSWORD not in caplog.text
    assert account.password_hash not in caplog.text
    assert response.json()["access_token"] not in caplog.text
