from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.responses import ok
from app.core.database import get_db
from app.core.errors import ErrorCode, NotFoundError
from app.models.user import User
from app.repositories.report_repository import ReportRepository
from app.schemas.common import ReportGenerateRequest, ReportResponse
from app.services.report_engine import ReportEngine

router = APIRouter(prefix="/reports", tags=["reports"])

report_engine = ReportEngine(ReportRepository())


@router.get("")
async def list_reports(
    request: Request,
    type: str | None = None,
    dimension: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    reports = await report_engine.list(session, user.id, type, dimension, limit, offset)
    return ok(request, [ReportResponse.model_validate(report) for report in reports])


@router.post("/generate")
async def generate_report(
    request: Request,
    body: ReportGenerateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Build the report for a period, refreshing it in place if it exists.

    Idempotent: the same ``(type, dimension, period)`` never yields two rows.
    """
    report = await report_engine.generate(
        session,
        user.id,
        body.type.value,
        period_start=body.period_start,
        period_end=body.period_end,
        dimension=body.dimension.value if body.dimension else None,
    )
    return ok(request, ReportResponse.model_validate(report))


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    report = await report_engine.get(session, user.id, report_id)
    if report is None:
        raise NotFoundError(ErrorCode.REPORT_NOT_FOUND, "Report not found")
    return ok(request, ReportResponse.model_validate(report))


@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    deleted = await report_engine.delete(session, user.id, report_id)
    if not deleted:
        raise NotFoundError(ErrorCode.REPORT_NOT_FOUND, "Report not found")
    return ok(request, {"deleted": True})
