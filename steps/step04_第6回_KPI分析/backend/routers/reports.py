"""報告書 CRUD — /api/reports(docs/04 §2)。"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session

from database import get_db
from models import DefectReport
from schemas import ReportCreate, ReportList, ReportOut, ReportUpdate
from services import rag

router = APIRouter(prefix="/api/reports", tags=["reports"])

# ソート指定に使えるカラム
_SORTABLE = {
    "occurrence_date": DefectReport.occurrence_date,
    "report_date": DefectReport.report_date,
    "defect_id": DefectReport.defect_id,
    "severity": DefectReport.severity,
    "created_at": DefectReport.created_at,
    "total_cost": DefectReport.total_cost,
}


def _next_defect_id(db: Session) -> str:
    """`KZ25-` + 連番で採番する。"""
    max_n = 0
    for (defect_id,) in db.query(DefectReport.defect_id).all():
        m = re.match(r"KZ25-(\d+)", defect_id or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"KZ25-{max_n + 1:04d}"


def _sum_costs(data: dict) -> float | None:
    parts = [
        data.get("material_cost"),
        data.get("processing_cost"),
        data.get("outsourcing_cost"),
        data.get("other_cost"),
    ]
    vals = [float(p) for p in parts if p is not None]
    return sum(vals) if vals else None


@router.get("", response_model=ReportList)
def list_reports(
    db: Session = Depends(get_db),
    q: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    machine: str | None = None,
    process: str | None = None,
    category_4m: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = "-occurrence_date",
):
    """一覧(フィルタ・ソート・ページング)。"""
    query = db.query(DefectReport)

    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                DefectReport.defect_id.like(like),
                DefectReport.part_number.like(like),
                DefectReport.part_name.like(like),
                DefectReport.defect_description.like(like),
            )
        )
    if status:
        query = query.filter(DefectReport.status == status)
    if severity:
        query = query.filter(DefectReport.severity == severity)
    if machine:
        query = query.filter(DefectReport.machine_name == machine)
    if process:
        query = query.filter(DefectReport.process == process)
    if category_4m:
        query = query.filter(DefectReport.category_4m == category_4m)
    if date_from:
        query = query.filter(DefectReport.occurrence_date >= date_from)
    if date_to:
        query = query.filter(DefectReport.occurrence_date <= date_to)

    total = query.count()

    # ソート("-" 始まりは降順)
    field = sort[1:] if sort.startswith("-") else sort
    column = _SORTABLE.get(field, DefectReport.occurrence_date)
    order = desc if sort.startswith("-") else asc
    query = query.order_by(order(column))

    items = query.offset(offset).limit(limit).all()
    return {"total": total, "items": items}


@router.post("", response_model=ReportOut, status_code=201)
def create_report(payload: ReportCreate, db: Session = Depends(get_db)):
    """新規作成。defect_id 未指定なら採番し、Chroma へ upsert。"""
    data = payload.model_dump(exclude_unset=False)

    if not data.get("defect_id"):
        data["defect_id"] = _next_defect_id(db)
    elif db.query(DefectReport).filter_by(defect_id=data["defect_id"]).first():
        raise HTTPException(status_code=409, detail="defect_id が既に存在します")

    if data.get("total_cost") is None:
        data["total_cost"] = _sum_costs(data)

    report = DefectReport(**data)
    db.add(report)
    db.commit()
    db.refresh(report)

    rag.upsert(report)
    return report


@router.get("/{defect_id}", response_model=ReportOut)
def get_report(defect_id: str, db: Session = Depends(get_db)):
    """詳細(defect_rate 含む)。"""
    report = db.query(DefectReport).filter_by(defect_id=defect_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="報告書が見つかりません")
    return report


@router.put("/{defect_id}", response_model=ReportOut)
def update_report(defect_id: str, payload: ReportUpdate, db: Session = Depends(get_db)):
    """部分更新(渡されたフィールドのみ)。Chroma 再 upsert。"""
    report = db.query(DefectReport).filter_by(defect_id=defect_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="報告書が見つかりません")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(report, key, value)

    db.commit()
    db.refresh(report)

    rag.upsert(report)
    return report


@router.delete("/{defect_id}", status_code=204)
def delete_report(defect_id: str, db: Session = Depends(get_db)):
    """削除(Chroma からも削除)。"""
    report = db.query(DefectReport).filter_by(defect_id=defect_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="報告書が見つかりません")
    db.delete(report)
    db.commit()
    rag.delete(defect_id)
    return None
