"""ダッシュボード統計 — /api/dashboard(docs/04 §4)。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from services import stats

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/statistics")
def get_statistics(
    db: Session = Depends(get_db),
    date_from: str | None = None,
    date_to: str | None = None,
):
    """KPI・月次推移・パレート・各種内訳を返す。"""
    return stats.statistics(db, date_from, date_to)


@router.get("/control-chart")
def get_control_chart(db: Session = Depends(get_db), months: int = Query(12, ge=1, le=36)):
    """p管理図(不適合率の管理図)。"""
    return stats.control_chart(db, months)
