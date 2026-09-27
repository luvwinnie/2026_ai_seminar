"""AIチャット — /api/chat(第4回)。

この回は RAG(報告書検索)を組み込まない「素のチャット」。
システムプロンプト + 会話履歴 + SSE ストリーミングに集中する。
sources イベントは空配列で送る(RAG は第5回で追加)。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from schemas import ChatRequest, ChatResponse
from services import llm

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(event: str, data: dict) -> str:
    """SSE 1イベントを整形する。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
def chat_stream(payload: ChatRequest):
    """SSE ストリーミングチャット。イベント: sources / token / done / error。"""

    def generate():
        try:
            # この回は RAG 未実装のため参照ソースは空
            yield _sse("sources", {"items": []})

            if not llm.is_configured():
                yield _sse("error", {"detail": "ANTHROPIC_API_KEY が設定されていません"})
                return

            history = [m.model_dump() for m in payload.history]
            # 文脈なし(空文字)で素のチャットを行う
            for text in llm.chat_stream(payload.message, history, ""):
                yield _sse("token", {"text": text})

            yield _sse("done", {})
        except Exception as exc:  # noqa: BLE001 — 例外は error イベントで通知
            yield _sse("error", {"detail": str(exc)})

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    """非ストリーミング版(テスト用)。sources は空。"""
    if not llm.is_configured():
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY が設定されていません")

    history = [m.model_dump() for m in payload.history]
    answer = llm.chat(payload.message, history, "")
    return {"answer": answer, "sources": []}
