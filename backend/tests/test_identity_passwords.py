import pytest
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.identity import normalize_email
from app.core.passwords import hash_password, verify_and_rehash, verify_password


def test_normalization():
    assert normalize_email("  Admin@Empresa.COM \n") == "admin@empresa.com"


def test_password_hashing():
    password = "a long test password"
    hashed = hash_password(password)
    assert hashed != password
    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed)
    assert not verify_password("wrong password", hashed)
    assert not verify_password(password, "not-a-hash")


@pytest.mark.parametrize("password", ["short", "a" * 129])
def test_password_policy(password):
    with pytest.raises(ValueError, match="12 and 128"):
        hash_password(password)


def test_old_parameters_are_rehashed():
    legacy = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8192, parallelism=1),))
    password = "a long test password"
    previous = legacy.hash(password)
    valid, replacement = verify_and_rehash(password, previous)
    assert valid
    assert replacement is not None and replacement != previous
    assert verify_password(password, replacement)
