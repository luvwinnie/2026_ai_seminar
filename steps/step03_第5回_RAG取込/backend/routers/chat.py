"""AIチャット(RAG)— /api/chat(docs/04 §6)。

この回で RAG 化: Chroma(またはキーワード)で上位5件を検索し、
回答前に sources を送り、本文で [KZ25-XXXX] を引用する。
(集計系質問への SQL 集計文脈の付与は第6回の統計機能で追加する)
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from schemas import ChatRequest, ChatResponse
from services import llm, rag

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _build_context(db: Session, message: str) -> tuple[str, list[dict]]:
    """RAG 検索(上位5件)を文脈として組み立てる。"""
    sources = rag.search(db, message, top_k=5)
    lines = []
    for s in sources:
        lines.append(
            f"[{s['defect_id']}] 部品:{s.get('part_name')} 現象:{s.get('phenomenon')} — {s['snippet']}"
        )
    context = "\n".join(lines) if lines else "(該当する報告書は見つかりませんでした)"
    return context, sources


def _sse(event: str, data: dict) -> str:
    """SSE 1イベントを整形する。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _source_items(sources: list[dict]) -> list[dict]:
    return [
        {
            "defect_id": s["defect_id"],
            "part_name": s.get("part_name"),
            "phenomenon": s.get("phenomenon"),
            "snippet": s["snippet"],
            "score": s["score"],
        }
        for s in sources
    ]


@router.post("/stream")
def chat_stream(payload: ChatRequest):
    """SSE ストリーミングチャット。イベント: sources / token / done / error。"""

    def generate():
        db = SessionLocal()
        try:
            context, sources = _build_context(db, payload.message)

            # 回答前に参照ソースを1回送る
            yield _sse("sources", {"items": _source_items(sources)})

            if not llm.is_configured():
                yield _sse("error", {"detail": "ANTHROPIC_API_KEY が設定されていません"})
                return

            history = [m.model_dump() for m in payload.history]
            for text in llm.chat_stream(payload.message, history, context):
                yield _sse("token", {"text": text})

            yield _sse("done", {})
        except Exception as exc:  # noqa: BLE001 — 例外は error イベントで通知
            yield _sse("error", {"detail": str(exc)})
        finally:
            db.close()

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    """非ストリーミング版(テスト用)。"""
    context, sources = _build_context(db, payload.message)

    if not llm.is_configured():
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY が設定されていません")

    history = [m.model_dump() for m in payload.history]
    answer = llm.chat(payload.message, history, context)
    return {"answer": answer, "sources": _source_items(sources)}
