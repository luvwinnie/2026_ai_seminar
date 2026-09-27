"""UIコントロール SSE — ブラウザが購読し、AIの画面操作イベントを受け取る。

フロントエンドの UiControlBridge が EventSource('/api/ui/events') で接続する。
イベントは services/ui_bus.py 経由で MCP ツールから届く。
"""
from __future__ import annotations

import json
import queue

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from services import ui_bus

router = APIRouter(prefix="/api/ui", tags=["ui"])


@router.get("/events")
def ui_events():
    """AI画面操作イベントの SSE ストリーム(15秒ごとに keep-alive コメント)。"""
    q = ui_bus.subscribe()

    def generate():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    ev = q.get(timeout=15)
                except queue.Empty:
                    yield ": ping\n\n"  # keep-alive
                    continue
                yield f"event: ui\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            ui_bus.unsubscribe(q)

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# REST 版の画面操作(MCPツールと同一実装 services/ui_control.py を使用)。
# 用途: LLMを介さない動作検証(全ページ総当たりE2E)・外部連携。ローカル前提。
# ---------------------------------------------------------------------------
from pydantic import BaseModel  # noqa: E402

from services import ui_control  # noqa: E402


class NavigateBody(BaseModel):
    page: str
    params: dict = {}


class CommandBody(BaseModel):
    name: str
    params: dict = {}
    path: str | None = None


@router.post("/navigate")
def ui_rest_navigate(body: NavigateBody):
    """MCPの ui_navigate と同じ画面遷移をRESTで発行する(検証・外部連携用)。"""
    return ui_control.navigate(body.page, **body.params)


@router.post("/open_report/{defect_id}")
def ui_rest_open_report(defect_id: str):
    return ui_control.open_report(defect_id)


@router.post("/command")
def ui_rest_command(body: CommandBody):
    """画面内コマンド(edit / run_4m / set_theme 等)をRESTで発行する(検証用)。"""
    return ui_control.command(body.name, body.params, path=body.path)
