from datetime import date
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.models.enums import BECType, Role


class DailyAlerts(BaseModel):
    date: date
    count: int


class TypeCount(BaseModel):
    bec_type: BECType
    count: int


class DashboardSummary(BaseModel):
    emails_total: int
    analyses_completed: int
    analyses_error: int
    alerts: dict[str, int]
    verdicts: dict[str, int]
    risk_distribution: dict[str, int]
    bec_type_distribution: list[TypeCount]
    alerts_last_7_days: list[DailyAlerts]


class AuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    actor_user_id: UUID | None
    actor_name: str | None
    actor_role: Role | None
    action: str
    resource_type: str | None
    resource_id: UUID | None
    ip_address: str | None
    created_at: AwareDatetime
    details: dict[str, str] | None
