from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select

from app.api.dependencies import require_automation_key
from app.api.email_analysis import get_analyzer_factory
from app.api.emails import Database
from app.models import BECAlert
from app.models.enums import AnalysisStatus
from app.schemas.automation import AutomationAnalysisResponse, AutomationIngestResponse
from app.schemas.email import EmailIngestRequest
from app.services.email_analysis import analyze_email
from app.services.email_ingestion import ingest_email_idempotently
from app.services.semantic_analysis import LLMErrorCode, SemanticAnalyzer

router = APIRouter(
    prefix="/api/automation/emails",
    tags=["n8n automation"],
    dependencies=[Depends(require_automation_key)],
)


@router.post(
    "",
    response_model=AutomationIngestResponse,
    responses={201: {"model": AutomationIngestResponse}},
)
def ingest(body: EmailIngestRequest, session: Database, request: Request, response: Response):
    email, created = ingest_email_idempotently(
        session, body, peer=request.client.host if request.client else None
    )
    response.status_code = 201 if created else 200
    return {"created": created, "email": email}


@router.post(
    "/{email_id}/analyze",
    response_model=AutomationAnalysisResponse,
    responses={
        502: {"model": AutomationAnalysisResponse},
        503: {"model": AutomationAnalysisResponse},
    },
)
def analyze(
    email_id: UUID,
    session: Database,
    request: Request,
    response: Response,
    analyzer_factory: Annotated[Callable[[], SemanticAnalyzer], Depends(get_analyzer_factory)],
):
    analysis = analyze_email(
        session,
        email_id,
        actor=None,
        analyzer_factory=analyzer_factory,
        peer=request.client.host if request.client else None,
    )
    alert_id = None
    if analysis.status == AnalysisStatus.ERROR:
        response.status_code = 503 if analysis.error_code == LLMErrorCode.NOT_CONFIGURED else 502
    else:
        alert_id = session.scalar(select(BECAlert.id).where(BECAlert.analysis_id == analysis.id))
    return {"analysis": analysis, "alert_id": alert_id}
