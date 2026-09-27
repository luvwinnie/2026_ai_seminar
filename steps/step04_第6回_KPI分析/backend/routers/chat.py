"""AIチャット(RAG)— /api/chat(docs/04 §6)。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from schemas import ChatRequest, ChatResponse
from services import llm, rag, stats

router = APIRouter(prefix="/api/chat", tags=["chat"])

# 集計系の質問を判定するキーワード
_AGG_KEYWORDS = ["件数", "合計", "平均", "集計", "ランキング", "最多", "トップ", "何件", "割合", "率"]


def _build_context(db: Session, message: str) -> tuple[str, list[dict]]:
    """RAG 検索(上位5件)+ 必要なら SQL 集計を文脈として組み立てる。"""
    sources = rag.search(db, message, top_k=5)

    lines = []
    for s in sources:
        lines.append(
            f"[{s['defect_id']}] 部品:{s.get('part_name')} 現象:{s.get('phenomenon')} — {s['snippet']}"
        )
    context = "\n".join(lines) if lines else "(該当する報告書は見つかりませんでした)"

    # 集計系の質問なら KPI サマリを追加
    if any(k in message for k in _AGG_KEYWORDS):
        kpi = stats.statistics(db)["kpi"]
        context += (
            "\n\n# 全体集計\n"
            f"総報告件数: {kpi['total_reports']} / 総不適合数: {kpi['total_defects']} / "
            f"不良率: {kpi['defect_rate']:.4f} / FPY: {kpi['fpy']:.4f} / "
            f"合計損失: {kpi['total_cost']} / 再発率: {kpi['recurrence_rate']:.4f} / "
            f"未対応: {kpi['open_count']}"
        )

    return context, sources


def _sse(event: str, data: dict) -> str:
    """SSE 1イベントを整形する。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
def chat_stream(payload: ChatRequest):
    """SSE ストリーミングチャット。イベント: sources / token / done / error。"""

    def generate():
        # 生成関数内で独立した DB セッションを使う(ストリーミング中も安全)
        db = SessionLocal()
        try:
            context, sources = _build_context(db, payload.message)

            # 回答前に参照ソースを1回送る
            source_items = [
                {
                    "defect_id": s["defect_id"],
                    "part_name": s.get("part_name"),
                    "phenomenon": s.get("phenomenon"),
                    "snippet": s["snippet"],
                    "score": s["score"],
                }
                for s in sources
            ]
            yield _sse("sources", {"items": source_items})

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

    source_items = [
        {
            "defect_id": s["defect_id"],
            "part_name": s.get("part_name"),
            "phenomenon": s.get("phenomenon"),
            "snippet": s["snippet"],
            "score": s["score"],
        }
        for s in sources
    ]
    return {"answer": answer, "sources": source_items}
