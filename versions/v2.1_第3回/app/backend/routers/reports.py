"""報告書の一覧と詳細（04_API設計書.md §4）。絞り込みの処理は services/report_service.py（MCP の道具と共通）。"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas import ReportList, ReportOut
from services import report_service

router = APIRouter(prefix="/api/reports")


@router.get("", response_model=ReportList)
def list_reports(
    q: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    machine: str | None = None,
    process: str | None = None,
    customer: str | None = None,
    operator: str | None = None,
    phenomenon: str | None = None,
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
    total, items = report_service.list_reports(
        db, limit=limit, offset=offset, sort=sort, q=q, date_from=date_from, date_to=date_to,
        status=status, severity=severity, machine=machine, process=process, customer=customer,
        operator=operator, phenomenon=phenomenon, category_4m=category_4m,
    )
    return {"total": total, "items": items}


@router.get("/{defect_id}", response_model=ReportOut)
def get_report(defect_id: str, db: Session = Depends(get_db)):
    report = report_service.get_report(db, defect_id)
    if report is None:
        raise HTTPException(status_code=404, detail="報告書が見つかりません")
    return report
