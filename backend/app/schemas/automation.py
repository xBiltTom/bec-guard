from uuid import UUID

from pydantic import BaseModel

from app.schemas.analysis import EmailAnalysisResponse
from app.schemas.email import EmailDetailResponse


class AutomationIngestResponse(BaseModel):
    created: bool
    email: EmailDetailResponse


class AutomationAnalysisResponse(BaseModel):
    analysis: EmailAnalysisResponse
    alert_id: UUID | None
