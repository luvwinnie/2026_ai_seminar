"""CAPA・8Dレポート REST(docs/10 A-3) — /api/capa。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import EightDReport
from services import capa_service
from services.capa_service import CapaError

router = APIRouter(prefix="/api/capa", tags=["capa"])


class CapaCreate(BaseModel):
    defect_id: str
    title: str
    action_type: str = "corrective"
    description: str | None = None
    owner: str | None = None
    due_date: str | None = None


class CapaUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    owner: str | None = None
    due_date: str | None = None
    status: str | None = None
    effect_note: str | None = None
    action_type: str | None = None


def _wrap(fn):
    try:
        return fn()
    except CapaError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("")
def list_capa(
    db: Session = Depends(get_db),
    status: str | None = None,
    defect_id: str | None = None,
    overdue: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    items = capa_service.list_actions(db, status=status, defect_id=defect_id, overdue=overdue, limit=limit)
    return {"total": len(items), "items": items}


@router.post("", status_code=201)
def create_capa(body: CapaCreate, db: Session = Depends(get_db)):
    return _wrap(lambda: capa_service.to_dict(capa_service.create(db, body.model_dump())))


@router.put("/{capa_id}")
def update_capa(capa_id: str, body: CapaUpdate, db: Session = Depends(get_db)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return _wrap(lambda: capa_service.to_dict(capa_service.update(db, capa_id, patch)))


@router.post("/draft/{defect_id}")
def draft_capa(defect_id: str, db: Session = Depends(get_db)):
    """AIによる処置ドラフト(保存しない。採用は利用者/明示依頼で)。"""
    return _wrap(lambda: capa_service.draft_actions(db, defect_id))


@router.post("/eight_d/{defect_id}", status_code=201)
def generate_eight_d(defect_id: str, db: Session = Depends(get_db)):
    rep = _wrap(lambda: capa_service.generate_8d(db, defect_id))
    return {"id": rep.id, "defect_id": rep.defect_id, "content_md": rep.content_md,
            "ai_backend": rep.ai_backend, "created_at": rep.created_at.isoformat()}


@router.get("/eight_d/{defect_id}")
def list_eight_d(defect_id: str, db: Session = Depends(get_db)):
    rows = (db.query(EightDReport).filter_by(defect_id=defect_id)
            .order_by(EightDReport.id.desc()).limit(10).all())
    return {"items": [{"id": r.id, "content_md": r.content_md, "ai_backend": r.ai_backend,
                       "created_at": r.created_at.isoformat()} for r in rows]}
