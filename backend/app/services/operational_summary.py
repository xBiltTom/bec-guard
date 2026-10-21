"""Operational SQL aggregates shared by dashboard and reports; no dataset imports."""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BECAlert, Email, EmailAnalysis


def date_conditions(column, from_date: date | None, to_date: date | None) -> list:
    conditions = []
    if from_date:
        conditions.append(column >= datetime.combine(from_date, time.min, UTC))
    if to_date:
        if to_date == date.max:
            conditions.append(column <= datetime.max.replace(tzinfo=UTC))
        else:
            conditions.append(column < datetime.combine(to_date + timedelta(days=1), time.min, UTC))
    return conditions


def operational_summary(
    session: Session, from_date: date | None = None, to_date: date | None = None
) -> dict:
    def counts(column, model, timestamp):
        return dict(
            session.execute(
                select(column, func.count())
                .select_from(model)
                .where(*date_conditions(timestamp, from_date, to_date))
                .group_by(column)
            ).all()
        )

    analyses = counts(EmailAnalysis.status, EmailAnalysis, EmailAnalysis.analyzed_at)
    alerts = counts(BECAlert.status, BECAlert, BECAlert.created_at)
    verdicts = counts(BECAlert.verdict, BECAlert, BECAlert.created_at)
    risks = counts(EmailAnalysis.risk_level, EmailAnalysis, EmailAnalysis.analyzed_at)
    types = counts(EmailAnalysis.bec_type, EmailAnalysis, EmailAnalysis.analyzed_at)
    return {
        "emails_total": session.scalar(
            select(func.count())
            .select_from(Email)
            .where(*date_conditions(Email.ingested_at, from_date, to_date))
        ),
        "analyses_completed": analyses.get("COMPLETED", 0),
        "analyses_error": analyses.get("ERROR", 0),
        "alerts": {key.lower(): alerts.get(key, 0) for key in ("OPEN", "UNDER_REVIEW", "CLOSED")},
        "verdicts": {
            key.lower(): verdicts.get(key, 0) for key in ("CONFIRMED_BEC", "FALSE_POSITIVE")
        },
        "risk_distribution": {
            key: risks.get(key, 0) for key in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        },
        "bec_type_distribution": [
            {"bec_type": key, "count": count}
            for key, count in sorted(types.items(), key=lambda item: item[0] or "")
            if key is not None
        ],
    }
