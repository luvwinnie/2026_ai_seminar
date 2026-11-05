"""報告書の一覧と詳細（04_API設計書.md §4）。"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from database import get_db
from models import DefectReport
from schemas import ReportList, ReportOut

router = APIRouter(prefix="/api/reports")

# 重大度は重さの順で並べる（文字列の順では並べない）
SEVERITY_RANK = case(
    {"low": 1, "medium": 2, "high": 3, "critical": 4},
    value=DefectReport.severity,
    else_=0,
)

SORT_COLUMNS = {
    "occurrence_date": DefectReport.occurrence_date,
    "report_date": DefectReport.report_date,
    "defect_id": DefectReport.defect_id,
    "severity": SEVERITY_RANK,
    "created_at": DefectReport.created_at,
    "total_cost": DefectReport.total_cost,
    "defect_count": DefectReport.defect_count,
}


def order_by_for(sort: str):
    """sort の値から並べ替えを作る。同じ値どうしは defect_id で、同じ向きに並べる。"""
    descending = sort.startswith("-")
    column = SORT_COLUMNS.get(sort.lstrip("-"), DefectReport.occurrence_date)
    if descending:
        return [column.desc(), DefectReport.defect_id.desc()]
    return [column.asc(), DefectReport.defect_id.asc()]


@router.get("", response_model=ReportList)
def list_reports(
    q: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    machine: str | None = None,
    process: str | None = None,
    category_4m: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = "-occurrence_date",
    db: Session = Depends(get_db),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail=[{
                "type": "date_range",
                "loc": ["query", "date_from"],
                "msg": "date_from is after date_to",
                "input": date_from.isoformat(),
            }],
        )

    # 条件はすべて AND で組む
    conditions = []
    if q and q.strip():
        keyword = q.strip()
        conditions.append(or_(
            DefectReport.defect_id.icontains(keyword, autoescape=True),
            DefectReport.part_number.icontains(keyword, autoescape=True),
            DefectReport.part_name.icontains(keyword, autoescape=True),
            DefectReport.defect_description.icontains(keyword, autoescape=True),
        ))
    if status:
        conditions.append(DefectReport.status == status)
    if severity:
        conditions.append(DefectReport.severity == severity)
    if machine:
        conditions.append(DefectReport.machine_name == machine)
    if process:
        conditions.append(DefectReport.process == process)
    if category_4m:
        conditions.append(DefectReport.category_4m == category_4m)
    if date_from:
        conditions.append(DefectReport.occurrence_date >= date_from)
    if date_to:
        conditions.append(DefectReport.occurrence_date <= date_to)

    total = db.scalar(select(func.count()).select_from(DefectReport).where(*conditions))
    items = db.scalars(
        select(DefectReport).where(*conditions).order_by(*order_by_for(sort)).limit(limit).offset(offset)
    ).all()
    return {"total": total, "items": items}


@router.get("/{defect_id}", response_model=ReportOut)
def get_report(defect_id: str, db: Session = Depends(get_db)):
    report = db.scalar(select(DefectReport).where(DefectReport.defect_id == defect_id))
    if report is None:
        raise HTTPException(status_code=404, detail="報告書が見つかりません")
    return report
