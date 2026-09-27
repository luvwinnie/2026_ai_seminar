"""チャット回答フィードバック REST — /api/chat/feedback。

👍/👎(+任意コメント)を保存する。集計は週次ダイジェスト(services/digest.py)と
GET で参照でき、モデル・プロンプト改善の材料にする(試用段階の一般的な改善ループ)。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import ChatFeedback
from services import telemetry

router = APIRouter(prefix="/api/chat/feedback", tags=["feedback"])


class FeedbackIn(BaseModel):
    session_id: int | None = None
    message_index: int | None = None
    rating: int = Field(..., description="+1(役に立った) / -1(問題あり)")
    trace_id: str | None = None
    comment: str | None = None
    answer_excerpt: str | None = None
    question_excerpt: str | None = None


def _to_dict(f: ChatFeedback) -> dict:
    return {
        "id": f.id,
        "trace_id": f.trace_id,
        "session_id": f.session_id,
        "message_index": f.message_index,
        "rating": f.rating,
        "comment": f.comment,
        "answer_excerpt": f.answer_excerpt,
        "question_excerpt": f.question_excerpt,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


@router.post("", status_code=201)
def create_feedback(body: FeedbackIn, db: Session = Depends(get_db)):
    if body.rating not in (1, -1):
        raise HTTPException(422, "rating は +1 か -1")
    row = ChatFeedback(
        trace_id=body.trace_id,
        session_id=body.session_id,
        message_index=body.message_index,
        rating=body.rating,
        comment=(body.comment or "").strip() or None,
        answer_excerpt=(body.answer_excerpt or "")[:500] or None,
        question_excerpt=(body.question_excerpt or "")[:300] or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    # Langfuse にもスコアとして記録(未設定なら no-op)
    telemetry.record_feedback(body.trace_id, body.rating, body.comment)
    return _to_dict(row)


@router.get("")
def list_feedback(db: Session = Depends(get_db), limit: int = 100):
    rows = db.query(ChatFeedback).order_by(ChatFeedback.id.desc()).limit(min(limit, 500)).all()
    ups = db.query(ChatFeedback).filter(ChatFeedback.rating > 0).count()
    downs = db.query(ChatFeedback).filter(ChatFeedback.rating < 0).count()
    return {"up": ups, "down": downs, "items": [_to_dict(f) for f in rows]}
