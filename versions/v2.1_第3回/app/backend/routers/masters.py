"""マスタ（04_API設計書.md §5）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from schemas import MastersOut
from services import report_service

router = APIRouter(prefix="/api/masters")


@router.get("", response_model=MastersOut)
def list_masters(db: Session = Depends(get_db)):
    return report_service.masters_with_usage(db)
