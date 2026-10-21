from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Email, User
from app.schemas.email import EmailIngestRequest
from app.services.audit import record_email_ingested


def ingest_email(
    session: Session, data: EmailIngestRequest, *, actor: User, peer: str | None = None
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
