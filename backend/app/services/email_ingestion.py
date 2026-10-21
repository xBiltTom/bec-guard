from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Email, User
from app.schemas.email import EmailIngestRequest
from app.services.audit import record_email_ingested


def ingest_email(
    session: Session, data: EmailIngestRequest, *, actor: User | None, peer: str | None = None
) -> Email:
    email = Email(**data.model_dump())
    session.add(email)
    try:
        session.flush()
        record_email_ingested(session, actor=actor, email_id=email.id, peer=peer)
        session.commit()
    except SQLAlchemyError as error:
        session.rollback()
        if (
            isinstance(error, IntegrityError)
            and getattr(error.orig, "sqlstate", None) == "23505"
            and getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            == "uq_emails_message_id"
        ):
            raise HTTPException(409, "Message-ID already exists") from None
        raise
    return email


def ingest_email_idempotently(
    session: Session, data: EmailIngestRequest, *, peer: str | None = None
) -> tuple[Email, bool]:
    statement = select(Email).where(Email.message_id == data.message_id)
    existing = session.scalar(statement)
    if existing is not None:
        return existing, False
    try:
        return ingest_email(session, data, actor=None, peer=peer), True
    except HTTPException as error:
        if error.status_code != 409:
            raise
        # Another transaction won the UNIQUE Message-ID race. ingest_email has
        # rolled back; READ COMMITTED can now see the committed winner.
        return session.execute(statement).scalar_one(), False
