"""Langfuse 可観測性の薄いラッパー(LLM アプリの一般的なトレース運用)。

チャット1リクエスト = 1トレース:
  trace(chat) ─ span(rag_sources)     … 事前RAG注入(ヒットIDとスコア)
             └ generation(opencode)   … 生成本体(回答・使用ツール)
  score(user-feedback)                … 画面の 👍/👎(routers/feedback.py 経由)

方針:
  - LANGFUSE_* が未設定/SDK未導入/サーバー不通でも本体を一切止めない(全てtry/except+no-op)
  - trace_id はチャットSSEの done イベントで画面に渡し、フィードバックと紐づける
"""
from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)

_client = None
_failed = False
_lock = threading.Lock()


def _get_client():
    """Langfuse クライアント(遅延初期化)。使えないときは None。"""
    global _client, _failed
    if _client is not None or _failed:
        return _client
    with _lock:
        if _client is not None or _failed:
            return _client
        host = os.getenv("LANGFUSE_HOST")
        pub = os.getenv("LANGFUSE_PUBLIC_KEY")
        sec = os.getenv("LANGFUSE_SECRET_KEY")
        if not (host and pub and sec):
            _failed = True
            return None
        try:
            from langfuse import Langfuse  # 遅延 import(任意依存)

            _client = Langfuse(public_key=pub, secret_key=sec, host=host, flush_interval=2.0)
        except Exception as exc:  # noqa: BLE001
            logger.info("Langfuse 無効(%s)", exc)
            _failed = True
    return _client


def is_enabled() -> bool:
    return _get_client() is not None


class ChatTrace:
    """チャット1件ぶんのトレース。Langfuse 不使用時は全メソッドが no-op。"""

    def __init__(self, message: str, session_id: int | None):
        self.trace_id: str | None = None
        self._trace = None
        lf = _get_client()
        if lf is None:
            return
        try:
            self._trace = lf.trace(
                name="chat",
                input=message,
                session_id=f"chat-session-{session_id}" if session_id else None,
                metadata={"app": "defectreport-ai"},
            )
            self.trace_id = self._trace.id
        except Exception:  # noqa: BLE001
            self._trace = None

    def sources(self, items: list[dict]) -> None:
        if self._trace is None:
            return
        try:
            self._trace.span(
                name="rag_sources",
                input=None,
                output=[{"defect_id": s.get("defect_id"), "score": s.get("score")} for s in items],
            ).end()
        except Exception:  # noqa: BLE001
            pass

    def finish(self, answer: str, tools: list[str], error: str | None = None) -> None:
        if self._trace is None:
            return
        try:
            self._trace.generation(
                name="opencode",
                model=os.getenv("OPENCODE_MODEL", "opencode"),
                output=answer[:4000],
                metadata={"tools": tools, "error": error},
            ).end()
            self._trace.update(output=answer[:4000], metadata={"tools": tools, "error": error})
        except Exception:  # noqa: BLE001
            pass


def record_feedback(trace_id: str | None, rating: int, comment: str | None) -> None:
    """👍/👎 を Langfuse スコアとして記録(trace_id があればトレースに紐づく)。"""
    lf = _get_client()
    if lf is None or not trace_id:
        return
    try:
        lf.score(trace_id=trace_id, name="user-feedback", value=float(rating), comment=comment or None)
    except Exception:  # noqa: BLE001
        pass


def triage_step(run_id: str, defect_id: str, name: str, output=None, metadata: dict | None = None,
                model: str | None = None) -> None:
    """トリアージの1ステップを記録する。run_id を trace id にし、承認の前後を同じトレースにまとめる。"""
    lf = _get_client()
    if lf is None:
        return
    try:
        trace = lf.trace(id=run_id, name="triage", input={"defect_id": defect_id},
                         metadata={"app": "defectreport-ai"})
        if model:
            # 判断モデルの呼び出しは generation として記録(モデル名・トークン・費用を Langfuse で見られる)
            trace.generation(name=name, model=model, output=output, metadata=metadata,
                             usage={"input": (metadata or {}).get("input_tokens", 0), "output": 0,
                                    "total_cost": (metadata or {}).get("cost_usd", 0.0)}).end()
        else:
            trace.span(name=name, output=output, metadata=metadata).end()
    except Exception:  # noqa: BLE001
        pass
