from sqlalchemy import exists, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.identity import validate_identity_email
from app.core.passwords import hash_password
from app.models import Role, User
from app.services.audit import AuditAction, record_security_event


class AdminBootstrapError(ValueError):
    pass


def create_initial_admin(session: Session, *, name: str, email: str, password: str) -> User:
    name = name.strip()
    if not 1 <= len(name) <= 200:
        raise ValueError("Name must contain between 1 and 200 characters")
    email = validate_identity_email(email)
    password_hash = hash_password(password)
    # Serialize bootstrap attempts: this command is not a general user creator.
    session.execute(text("LOCK TABLE public.users IN SHARE ROW EXCLUSIVE MODE"))
    if session.scalar(select(exists().where(User.role == Role.ADMIN))) or session.scalar(
        select(exists().where(User.email == email))
    ):
        session.rollback()
        raise AdminBootstrapError("An ADMIN already exists or the email is already in use")
    admin = User(name=name, email=email, password_hash=password_hash, role=Role.ADMIN)
    session.add(admin)
    try:
        session.flush()
        record_security_event(session, AuditAction.ADMIN_BOOTSTRAPPED, actor=admin)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise AdminBootstrapError(
            "An ADMIN already exists or the email is already in use"
        ) from None
    return admin
