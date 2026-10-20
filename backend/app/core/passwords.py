import secrets

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

password_hasher = PasswordHash.recommended()
dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


def validate_password(password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError("Password must contain between 12 and 128 characters")


def hash_password(password: str) -> str:
    validate_password(password)
    return password_hasher.hash(password)


def verify_and_rehash(password: str, stored_hash: str) -> tuple[bool, str | None]:
    if len(password) > MAX_PASSWORD_LENGTH:
        return False, None
    try:
        return password_hasher.verify_and_update(password, stored_hash)
    except UnknownHashError, ValueError:
        # Invalid/legacy placeholders must fail closed, with comparable hash work.
        password_hasher.verify(password, dummy_hash)
        return False, None


def verify_password(password: str, stored_hash: str) -> bool:
    return verify_and_rehash(password, stored_hash)[0]
