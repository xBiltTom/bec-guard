"""Privacy-limited operational snapshot, gathered only from PostgreSQL."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BECAlert, EmailAnalysis, User
from app.models.enums import AlertStatus, AlertVerdict, BECType, RiskLevel
from app.services.operational_summary import date_conditions, operational_summary


class ReportAlert(BaseModel):
    id: UUID
    created_at: AwareDatetime
    risk_score: int
    risk_level: RiskLevel
    bec_type: BECType | None
    status: AlertStatus
    verdict: AlertVerdict | None
    assigned_to_name: str | None


@dataclass
class OperationalReport:
    generated_at: datetime
    from_date: date | None
    to_date: date | None
    summary: dict
    alerts: list[ReportAlert]

    @property
    def period(self) -> str:
        start = self.from_date.isoformat() if self.from_date else "Inicio"
        end = self.to_date.isoformat() if self.to_date else "Actualidad"
        return f"{start} / {end} (UTC)"


def gather_report(
    session: Session, from_date: date | None = None, to_date: date | None = None
) -> OperationalReport:
    if from_date and to_date and from_date > to_date:
        raise ValueError("Invalid date range")
    statement = (
        select(
            BECAlert.id,
            BECAlert.created_at,
            EmailAnalysis.risk_score,
            EmailAnalysis.risk_level,
            EmailAnalysis.bec_type,
            BECAlert.status,
            BECAlert.verdict,
            User.name.label("assigned_to_name"),
        )
        .join(EmailAnalysis, BECAlert.analysis_id == EmailAnalysis.id)
        .outerjoin(User, BECAlert.assigned_to == User.id)
        .where(*date_conditions(BECAlert.created_at, from_date, to_date))
        .order_by(BECAlert.created_at.desc(), BECAlert.id)
    )
    summary = operational_summary(session, from_date, to_date)
    return OperationalReport(
        datetime.now(UTC),
        from_date,
        to_date,
        summary,
        [ReportAlert.model_validate(row) for row in session.execute(statement).mappings()],
    )
