"""OpenCode serve の HTTP API を呼ぶ（06_AI設計書.md §0.2・§1.2・§3.4、04_API設計書.md §6）。

1問ごとに OpenCode のセッションを作り、GET /event を購読してから prompt_async で送る。
/event には全セッションの出来事が流れるので、自分の sessionID のものだけを読む。
形は OpenCode 1.19.0 の GET /doc（OpenAPI）で確かめた。
"""

import json
import logging
import time
from collections.abc import AsyncIterator

import httpx2

logger = logging.getLogger(__name__)

EMPTY_RESPONSE = "OpenCodeが空応答を返しました(モデル未応答)。もう一度お試しください"
LENGTH_ERROR = "出力が上限で切れました（finish=length）"

# OpenCode に元からある道具（1.19.0 の GET /experimental/tool/ids）。チャットでは切り、MCP の道具だけを使わせる。
# question（利用者に聞き返す道具）はヘッドレスでは答える人がいないので必ず切る
BUILTIN_TOOLS = [
    "bash", "read", "glob", "grep", "edit", "write", "task", "webfetch",
    "todowrite", "websearch", "skill", "apply_patch", "question",
]

CONNECT_TIMEOUT = 10  # 秒
READ_TIMEOUT = 300  # 秒。ローカル LLM は次の出来事まで時間がかかることがある
TOTAL_TIMEOUT = 600  # 秒。1問の上限


class OpenCodeError(Exception):
    """OpenCode やモデルの失敗。メッセージをそのまま error イベントの detail にする。"""


def model_error(error: dict) -> str:
    """OpenCode の error（{name, data}）を、利用者に見せる理由にする。"""
    name = error.get("name", "")
    data = error.get("data") or {}
    if name == "MessageOutputLengthError":
        return f"OpenCode/モデルエラー: {LENGTH_ERROR}"
    message = data.get("message") or name or "不明なエラー"
    if data.get("statusCode"):
        message = f"{message}（HTTP {data['statusCode']}）"
    return f"OpenCode/モデルエラー: {message}"


class OpenCodeClient:
    def __init__(self, base_url: str, transport: httpx2.AsyncBaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    def _client(self) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            base_url=self.base_url,
            transport=self.transport,
            timeout=httpx2.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT),
        )

    async def stream(self, prompt: str, system: str, provider_id: str, model_id: str) -> AsyncIterator[tuple[str, dict]]:
        """1問を送り、("thinking"|"token"|"tool", data) を届いた順に返す。失敗は OpenCodeError。"""
        async with self._client() as client:
            response = await client.post("/session", json={"title": "DefectReport AI チャット"})
            response.raise_for_status()
            session_id = response.json()["id"]
            try:
                got_text = False
                async for kind, data in self._run(client, session_id, prompt, system, provider_id, model_id):
                    got_text = got_text or (kind == "token" and bool(data["text"]))
                    yield kind, data
                if not got_text:
                    # 逐次の差分が取れなかったときは、完了した回答を取り直す
                    text = await self._final_text(client, session_id)
                    if not text.strip():
                        raise OpenCodeError(EMPTY_RESPONSE)
                    yield "token", {"text": text}
            finally:
                try:
                    await client.delete(f"/session/{session_id}")  # 使い終わったセッションを消す（失敗しても無視する）
                except Exception:
                    logger.warning("OpenCode のセッション %s を消せませんでした", session_id)

    async def _run(self, client: httpx2.AsyncClient, session_id: str, prompt: str, system: str,
                   provider_id: str, model_id: str) -> AsyncIterator[tuple[str, dict]]:
        roles: dict[str, str] = {}  # messageID → user / assistant
        part_types: dict[str, str] = {}  # partID → text / reasoning / tool …
        emitted: dict[str, str] = {}  # partID → これまでに送った本文・推論
        tool_states: dict[str, tuple] = {}  # partID → (status, title)
        deadline = time.monotonic() + TOTAL_TIMEOUT

        async with client.stream("GET", "/event") as events:
            events.raise_for_status()
            lines = events.aiter_lines()
            # 購読が始まった（server.connected が届いた）のを確かめてから送る（取りこぼさない）
            async for line in lines:
                if line.startswith("data:"):
                    break
            body = {
                "parts": [{"type": "text", "text": prompt}],
                "system": system,
                "model": {"providerID": provider_id, "modelID": model_id},
                "tools": {name: False for name in BUILTIN_TOOLS},
            }
            response = await client.post(f"/session/{session_id}/prompt_async", json=body)
            if response.status_code >= 400:
                raise OpenCodeError(f"OpenCode/モデルエラー: プロンプトを送れませんでした（HTTP {response.status_code}）")

            async for line in lines:
                if time.monotonic() > deadline:
                    raise OpenCodeError("OpenCode の応答が時間内に終わりませんでした")
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:])
                kind = event.get("type")
                props = event.get("properties") or {}
                if props.get("sessionID", session_id) != session_id:
                    continue  # ほかのセッションの出来事

                if kind == "message.updated":
                    info = props["info"]
                    roles[info["id"]] = info["role"]
                    if info["role"] == "assistant":
                        if info.get("error"):
                            raise OpenCodeError(model_error(info["error"]))
                        if info.get("finish") == "length":
                            raise OpenCodeError(f"OpenCode/モデルエラー: {LENGTH_ERROR}")

                elif kind == "message.part.updated":
                    part = props["part"]
                    part_types[part["id"]] = part["type"]
                    if roles.get(part["messageID"]) == "user" or part.get("text") == prompt:
                        continue  # 送った質問（user の発言）は回答に入れない
                    if part["type"] == "tool":
                        state = part.get("state") or {}
                        current = (state.get("status"), state.get("title"))
                        if tool_states.get(part["id"]) != current:  # 状態が変わったときだけ送る
                            tool_states[part["id"]] = current
                            yield "tool", {"name": part["tool"], "status": current[0], "title": current[1]}
                    elif part["type"] in ("text", "reasoning") and not part.get("synthetic"):
                        # 差分（delta）で届かなかった残りを送る
                        text = part.get("text") or ""
                        sent = emitted.get(part["id"], "")
                        if text.startswith(sent) and len(text) > len(sent):
                            emitted[part["id"]] = text
                            yield ("thinking" if part["type"] == "reasoning" else "token"), {"text": text[len(sent):]}

                elif kind == "message.part.delta":
                    if props.get("field") != "text" or roles.get(props["messageID"]) == "user":
                        continue
                    delta = props.get("delta") or ""
                    if not delta:
                        continue
                    emitted[props["partID"]] = emitted.get(props["partID"], "") + delta
                    part_type = part_types.get(props["partID"])
                    yield ("thinking" if part_type == "reasoning" else "token"), {"text": delta}

                elif kind == "session.error":
                    raise OpenCodeError(model_error(props.get("error") or {}))

                elif kind == "session.idle":
                    return
        raise OpenCodeError("OpenCode との接続が途中で切れました")

    async def _final_text(self, client: httpx2.AsyncClient, session_id: str) -> str:
        """完了したメッセージから、最後の回答の本文をまとめて取る。"""
        response = await client.get(f"/session/{session_id}/message")
        response.raise_for_status()
        assistants = [m for m in response.json() if m["info"]["role"] == "assistant"]
        if not assistants:
            return ""
        last = assistants[-1]
        if last["info"].get("error"):
            raise OpenCodeError(model_error(last["info"]["error"]))
        return "".join(
            p.get("text") or "" for p in last["parts"] if p["type"] == "text" and not p.get("synthetic")
        )
