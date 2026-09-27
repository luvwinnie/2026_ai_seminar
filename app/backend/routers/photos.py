"""報告書の現場写真(docs/10 B-4) — /api/reports/{defect_id}/photos。

保存先はローカルディスク(backend/data/photos/{defect_id}/)。テーブルは持たず
ディレクトリ一覧を正とする(ローカル動作アプリの割り切り)。
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import BACKEND_DIR, get_db
from models import DefectReport
from services import llm

router = APIRouter(prefix="/api/reports/{defect_id}/photos", tags=["photos"])

PHOTOS_DIR = Path(os.getenv("PHOTOS_DIR", str(BACKEND_DIR / "data" / "photos")))
_ALLOWED = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
_MAX_BYTES = 8 * 1024 * 1024
_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(jpg|jpeg|png|webp)$")


def _check_report(db: Session, defect_id: str) -> None:
    if not db.query(DefectReport).filter_by(defect_id=defect_id).first():
        raise HTTPException(status_code=404, detail=f"{defect_id} は見つかりません")


def _dir(defect_id: str) -> Path:
    if not re.match(r"^KZ25-\d{4}$", defect_id):
        raise HTTPException(status_code=400, detail="不正な報告書ID")
    return PHOTOS_DIR / defect_id


def _safe_path(defect_id: str, name: str) -> Path:
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="不正なファイル名")
    return _dir(defect_id) / name


@router.get("")
def list_photos(defect_id: str, db: Session = Depends(get_db)):
    _check_report(db, defect_id)
    d = _dir(defect_id)
    items = []
    if d.exists():
        for f in sorted(d.iterdir()):
            if _NAME_RE.match(f.name):
                items.append({
                    "name": f.name,
                    "url": f"/api/reports/{defect_id}/photos/{f.name}",
                    "size": f.stat().st_size,
                })
    return {"items": items}


@router.post("", status_code=201)
async def upload_photo(defect_id: str, file: UploadFile, db: Session = Depends(get_db)):
    _check_report(db, defect_id)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED:
        raise HTTPException(status_code=415, detail=f"対応形式: {', '.join(_ALLOWED)}")
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="8MB以下にしてください")
    d = _dir(defect_id)
    d.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    (d / name).write_bytes(data)
    return {"name": name, "url": f"/api/reports/{defect_id}/photos/{name}", "size": len(data)}


@router.get("/{name}")
def get_photo(defect_id: str, name: str):
    path = _safe_path(defect_id, name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="写真が見つかりません")
    return FileResponse(path, media_type=_ALLOWED[path.suffix.lower()])


@router.delete("/{name}", status_code=204)
def delete_photo(defect_id: str, name: str):
    path = _safe_path(defect_id, name)
    if path.exists():
        path.unlink()


@router.post("/{name}/analyze")
def analyze_photo(defect_id: str, name: str, db: Session = Depends(get_db)):
    """AI外観アシスト — 写真の観察所見と現象分類の候補を返す(保存はしない)。"""
    _check_report(db, defect_id)
    path = _safe_path(defect_id, name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="写真が見つかりません")
    try:
        result = llm.describe_defect_photo(path.read_bytes(), _ALLOWED[path.suffix.lower()], name)
    except llm.LLMNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"name": name, **result}
