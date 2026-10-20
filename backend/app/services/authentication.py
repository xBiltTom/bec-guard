from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.identity import normalize_email
from app.core.passwords import dummy_hash, verify_and_rehash
from app.models import User


class AuthenticationFailed(Exception):
    def __init__(self, *, actor: User | None, inactive: bool = False):
        self.actor = actor
        self.inactive = inactive
        super().__init__("Invalid credentials")


def authenticate(session: Session, *, email: str, password: str) -> User:
    user = session.scalar(select(User).where(func.lower(User.email) == normalize_email(email)))
    valid, updated_hash = verify_and_rehash(password, user.password_hash if user else dummy_hash)
    if user is None or not valid or not user.is_active:
        raise AuthenticationFailed(actor=user, inactive=user is not None and not user.is_active)
    if updated_hash is not None:
        user.password_hash = updated_hash
    return user
