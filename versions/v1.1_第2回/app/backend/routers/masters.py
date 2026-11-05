"""マスタ（04_API設計書.md §5）。"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models import DefectReport, MasterItem
from schemas import MastersOut
from seed import MASTER_COLUMNS

router = APIRouter(prefix="/api/masters")


@router.get("", response_model=MastersOut)
def list_masters(db: Session = Depends(get_db)):
    result = {}
    for category, column_name in MASTER_COLUMNS.items():
        column = getattr(DefectReport, column_name)
        # 使用件数は保存せず、報告書の列で数える
        usage = dict(db.execute(select(column, func.count()).group_by(column)).all())
        items = db.scalars(
            select(MasterItem)
            .where(MasterItem.category == category)
            .order_by(MasterItem.sort_order, MasterItem.name)
        )
        result[category] = [
            {
                "id": item.id,
                "category": item.category,
                "name": item.name,
                "sort_order": item.sort_order,
                "is_active": item.is_active,
                "usage_count": usage.get(item.name, 0),
            }
            for item in items
        ]
    return result
