from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select

from app.api.emails import Database, Reader, Writer
from app.models import Email, EmailAnalysis
from app.models.enums import AnalysisStatus
from app.schemas.analysis import EmailAnalysisResponse
from app.services.email_analysis import analyze_email, create_semantic_analyzer
from app.services.semantic_analysis import LLMErrorCode, SemanticAnalyzer

router = APIRouter(prefix="/api/emails", tags=["BEC analysis"])


def get_analyzer_factory() -> Callable[[], SemanticAnalyzer]:
    # Return a factory: invalid/missing settings become a persisted ERROR, and a
    # completed analysis or missing email never needs provider configuration.
    return create_semantic_analyzer


@router.post(
    "/{email_id}/analyze",
    response_model=EmailAnalysisResponse,
    responses={502: {"model": EmailAnalysisResponse}, 503: {"model": EmailAnalysisResponse}},
)
def post_analysis(
    email_id: UUID,
    session: Database,
    actor: Writer,
    request: Request,
    response: Response,
    analyzer_factory: Annotated[Callable[[], SemanticAnalyzer], Depends(get_analyzer_factory)],
):
    analysis = analyze_email(
        session,
        email_id,
        actor=actor,
        analyzer_factory=analyzer_factory,
        peer=request.client.host if request.client else None,
    )
    if analysis.status == AnalysisStatus.ERROR:
        response.status_code = 503 if analysis.error_code == LLMErrorCode.NOT_CONFIGURED else 502
    return analysis


@router.get("/{email_id}/analysis", response_model=EmailAnalysisResponse)
def get_analysis(email_id: UUID, session: Database, _actor: Reader):
    if session.get(Email, email_id) is None:
        raise HTTPException(404, "Email not found")
    analysis = session.scalar(select(EmailAnalysis).where(EmailAnalysis.email_id == email_id))
    if analysis is None:
        raise HTTPException(404, "Email analysis not found")
    return analysis
