from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.models.enums import AlertStatus, AlertVerdict, BECType, RiskLevel
from app.schemas.analysis import EmailAnalysisResponse, Score


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_id: UUID
    status: AlertStatus
    verdict: AlertVerdict | None
    assigned_to: UUID | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class AlertSummaryResponse(AlertResponse):
    email_id: UUID
    risk_score: Score
    risk_level: RiskLevel
    bec_type: BECType | None
    sender_name: str | None
    sender_email: str
    subject: str
    received_at: AwareDatetime


class AlertDetailResponse(AlertResponse):
    resolution: str | None
    closed_at: AwareDatetime | None
    analysis: EmailAnalysisResponse
