"""週次品質ダイジェスト REST(docs/10 A-2) — /api/digests。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import WeeklyDigest
from services import digest as digest_service

router = APIRouter(prefix="/api/digests", tags=["digests"])


@router.get("")
def list_digests(db: Session = Depends(get_db), limit: int = Query(20, ge=1, le=100)):
    rows = db.query(WeeklyDigest).order_by(WeeklyDigest.id.desc()).limit(limit).all()
    return {"items": [digest_service.to_dict(d) for d in rows]}


@router.post("/generate", status_code=201)
def generate_digest(db: Session = Depends(get_db), days: int = Query(7, ge=1, le=90)):
    """直近 days 日のダイジェストを今すぐ生成する(cron からは本エンドポイントを叩く)。"""
    return digest_service.to_dict(digest_service.generate(db, days=days))


@router.get("/{digest_id}")
def get_digest(digest_id: int, db: Session = Depends(get_db)):
    d = db.query(WeeklyDigest).filter_by(id=digest_id).first()
    if d is None:
        raise HTTPException(status_code=404, detail="見つかりません")
    return digest_service.to_dict(d)
