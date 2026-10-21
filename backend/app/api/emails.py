from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from app.api.dependencies import require_roles
from app.core.database import get_session
from app.models import Email, Role, User
from app.schemas.email import EmailDetailResponse, EmailIngestRequest, EmailSummaryResponse
from app.services.email_ingestion import ingest_email

router = APIRouter(prefix="/api/emails", tags=["Email ingestion"])
Database = Annotated[Session, Depends(get_session)]
Reader = Annotated[User, Depends(require_roles(*Role))]
Writer = Annotated[User, Depends(require_roles(Role.ADMIN, Role.MANAGER, Role.ANALYST))]


@router.post("", response_model=EmailDetailResponse, status_code=201)
def create_email(body: EmailIngestRequest, session: Database, actor: Writer, request: Request):
    return ingest_email(
        session, body, actor=actor, peer=request.client.host if request.client else None
    )


@router.get("", response_model=list[EmailSummaryResponse])
def list_emails(
    session: Database,
    _actor: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    statement = (
        select(Email)
        .options(
            load_only(
                Email.id,
                Email.message_id,
                Email.sender_name,
                Email.sender_email,
                Email.reply_to,
                Email.subject,
                Email.received_at,
                Email.ingested_at,
            )
        )
        .order_by(Email.received_at.desc(), Email.id)
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


@router.get("/{email_id}", response_model=EmailDetailResponse)
def get_email(email_id: UUID, session: Database, _actor: Reader):
    email = session.get(Email, email_id)
    if email is None:
        raise HTTPException(404, "Email not found")
    return email
