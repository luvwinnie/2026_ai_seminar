from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from routers.chat import chat_backend
from models import DefectReport
from schemas import HealthOut

router = APIRouter()


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)):
    count = db.scalar(select(func.count()).select_from(DefectReport))
    return {"status": "ok", "reports": count, "chat_backend": chat_backend()}
