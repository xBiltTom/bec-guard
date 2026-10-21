from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.dependencies import require_roles
from app.api.emails import Database
from app.models import Role, User
from app.services.report_formats import pdf_bytes, xlsx_bytes
from app.services.reporting import gather_report

router = APIRouter(prefix="/api/reports", tags=["Operational reports"])
ReportReader = Annotated[User, Depends(require_roles(Role.ADMIN, Role.MANAGER, Role.AUDITOR))]


def report_response(session, extension, from_date, to_date):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(400, "Invalid date range")
    report = gather_report(session, from_date, to_date)
    try:
        content = pdf_bytes(report) if extension == "pdf" else xlsx_bytes(report)
    except OSError, ImportError:
        raise HTTPException(503, "Report generation unavailable") from None
    mime = (
        "application/pdf"
        if extension == "pdf"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    filename = f"bec-guard-operational-{report.generated_at:%Y%m%d}.{extension}"
    return Response(
        content,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/operational.pdf")
def operational_pdf(
    session: Database,
    _actor: ReportReader,
    from_date: date | None = None,
    to_date: date | None = None,
):
    return report_response(session, "pdf", from_date, to_date)


@router.get("/operational.xlsx")
def operational_xlsx(
    session: Database,
    _actor: ReportReader,
    from_date: date | None = None,
    to_date: date | None = None,
):
    return report_response(session, "xlsx", from_date, to_date)
