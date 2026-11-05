"""OpenCode serve の代わり（LLM を呼ばないチャットの試験用。07_試験・運用仕様書.md §1）。

形は OpenCode 1.19.0 の GET /doc（OpenAPI）に合わせた。質問の語で場面を選ぶ：
  「空応答」→ 空の応答、「402」→ モデルのエラー（info.error）、「上限」→ finish=length、
  「セッションエラー」→ session.error、「差分なし」→ 逐次の差分が無く完了した回答だけ、それ以外 → ふつうの回答。

pytest では FakeOpenCode().transport を OpenCodeClient に渡す。画面の試験では HTTP のサーバーとして起動する：
    cd app/backend && .venv/bin/uvicorn tests.fake_opencode:app --port <空いているポート>
"""

import asyncio
import json

import httpx2
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

ANSWER = (
    "**KZ25-0043** は 2025-09-13 に機械 a61nx（マシニング）で起きた表面キズです。"
    "客先は翠峰重工業で、加工数12個のうち3個が不適合（不良率 25%）でした。詳しくは [KZ25-0043] を見てください。"
)
THINKING = "KZ25-0043 を get_defect_report で取得する。"
TOOL = "defect-reports_get_defect_report"


def choose_scenario(prompt: str) -> str:
    question = prompt.split("# 質問")[-1]
    for keyword, scenario in [("空応答", "empty"), ("402", "model_error"), ("上限", "length"),
                              ("セッションエラー", "session_error"), ("差分なし", "no_delta")]:
        if keyword in question:
            return scenario
    return "normal"


def _assistant(sid: str, mid: str, **extra) -> dict:
    info = {"id": mid, "sessionID": sid, "role": "assistant", "providerID": "ollama", "modelID": "gemma4:26b"}
    return {"type": "message.updated", "properties": {"sessionID": sid, "info": {**info, **extra}}}


def _part(sid: str, mid: str, pid: str, type_: str, **extra) -> dict:
    part = {"id": pid, "sessionID": sid, "messageID": mid, "type": type_, **extra}
    return {"type": "message.part.updated", "properties": {"sessionID": sid, "part": part, "time": 0}}


def _delta(sid: str, mid: str, pid: str, text: str) -> dict:
    return {"type": "message.part.delta",
            "properties": {"sessionID": sid, "messageID": mid, "partID": pid, "field": "text", "delta": text}}


def _tool(sid: str, mid: str, status: str, title: str | None = None) -> dict:
    state = {"status": status, "input": {"defect_id": "KZ25-0043"}}
    if title:
        state["title"] = title
    return _part(sid, mid, "prt_tool", "tool", callID="call_1", tool=TOOL, state=state)


def scenario_events(scenario: str, sid: str, prompt: str) -> list[dict]:
    """1問ぶんの /event の出来事。ほかのセッションの出来事と、送った質問（user の発言）の出来事も混ぜる。"""
    user, mid = "msg_user", "msg_assistant"
    events = [
        {"type": "message.updated", "properties": {"sessionID": "ses_other", "info": {"id": "msg_x", "role": "assistant"}}},
        _delta("ses_other", "msg_x", "prt_x", "ほかのセッションの本文"),
        {"type": "message.updated", "properties": {"sessionID": sid, "info": {"id": user, "sessionID": sid, "role": "user"}}},
        _part(sid, user, "prt_user", "text", text=prompt),
        _assistant(sid, mid),
    ]
    if scenario == "normal":
        events += [
            _part(sid, mid, "prt_think", "reasoning", text=""),
            _delta(sid, mid, "prt_think", THINKING[:10]),
            _delta(sid, mid, "prt_think", THINKING[10:]),
            _tool(sid, mid, "pending"),
            _tool(sid, mid, "running"),
            _tool(sid, mid, "running"),  # 状態が変わらない更新は tool にしない
            _tool(sid, mid, "completed", title="KZ25-0043"),
            _part(sid, mid, "prt_text", "text", text=""),
            *[_delta(sid, mid, "prt_text", ANSWER[i:i + 20]) for i in range(0, len(ANSWER), 20)],
            _part(sid, mid, "prt_text", "text", text=ANSWER),  # 差分で送った分は二重に送らない
            _assistant(sid, mid, finish="stop"),
        ]
    elif scenario == "no_delta":
        events += [_tool(sid, mid, "completed", title="KZ25-0043"), _assistant(sid, mid, finish="stop")]
    elif scenario == "empty":
        events += [_assistant(sid, mid, finish="stop")]
    elif scenario == "model_error":
        error = {"name": "APIError", "data": {"message": "Insufficient credits", "statusCode": 402, "isRetryable": False}}
        events += [_assistant(sid, mid, error=error)]
    elif scenario == "length":
        events += [
            _part(sid, mid, "prt_text", "text", text=""),
            _delta(sid, mid, "prt_text", "途中までの本文"),
            _assistant(sid, mid, finish="length"),
        ]
    elif scenario == "session_error":
        events += [{"type": "session.error",
                    "properties": {"sessionID": sid, "error": {"name": "UnknownError", "data": {"message": "接続できません"}}}}]
    events.append({"type": "session.idle", "properties": {"sessionID": sid}})
    return events


def final_messages(scenario: str, sid: str) -> list[dict]:
    """GET /session/{id}/message の応答（完了した回答を取り直すとき）。"""
    parts = [{"id": "prt_text", "type": "text", "text": ANSWER}] if scenario == "no_delta" else []
    return [
        {"info": {"id": "msg_user", "sessionID": sid, "role": "user"}, "parts": []},
        {"info": {"id": "msg_assistant", "sessionID": sid, "role": "assistant"}, "parts": parts},
    ]


class FakeOpenCode:
    def __init__(self, delay: float = 0.0):
        self.delay = delay  # 出来事のあいだの待ち（画面で逐次表示を見るため）
        self.created: list[str] = []
        self.prompts: list[dict] = []
        self.deleted: list[str] = []
        self.scenarios: dict[str, str] = {}
        self._queue: asyncio.Queue | None = None

    def _events_queue(self) -> asyncio.Queue:
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue

    def create_session(self) -> dict:
        sid = f"ses_{len(self.created) + 1:04d}"
        self.created.append(sid)
        return {"id": sid}

    def prompt(self, sid: str, body: dict) -> None:
        self.prompts.append({"session": sid, **body})
        text = body["parts"][0]["text"]
        self.scenarios[sid] = choose_scenario(text)
        self._events_queue().put_nowait(scenario_events(self.scenarios[sid], sid, text))

    async def event_stream(self):
        yield b'data: {"type":"server.connected","properties":{}}\n\n'
        events = await self._events_queue().get()
        for event in events:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()

    async def handle(self, request: httpx2.Request) -> httpx2.Response:
        """httpx2.MockTransport の受け口。"""
        path, method = request.url.path, request.method
        if method == "POST" and path == "/session":
            return httpx2.Response(200, json=self.create_session())
        if method == "GET" and path == "/event":
            return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=self.event_stream())
        sid = path.split("/")[2] if path.startswith("/session/") else ""
        if method == "POST" and path.endswith("/prompt_async"):
            self.prompt(sid, json.loads(request.content))
            return httpx2.Response(204)
        if method == "GET" and path.endswith("/message"):
            return httpx2.Response(200, json=final_messages(self.scenarios.get(sid, "normal"), sid))
        if method == "DELETE":
            self.deleted.append(sid)
            return httpx2.Response(200, json=True)
        return httpx2.Response(404, json={"error": "not found"})

    @property
    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self.handle)


# 画面の試験（app/e2e）で使う HTTP のサーバー。逐次表示が見えるよう、出来事のあいだを少し空ける
fake = FakeOpenCode(delay=0.05)
app = FastAPI(title="fake opencode")


@app.get("/global/health")
def health():
    return {"healthy": True, "version": "fake"}


@app.post("/session")
def create_session():
    return fake.create_session()


@app.get("/event")
def events():
    return StreamingResponse(fake.event_stream(), media_type="text/event-stream")


@app.post("/session/{sid}/prompt_async")
async def prompt_async(sid: str, request: Request):
    fake.prompt(sid, await request.json())
    return Response(status_code=204)


@app.get("/session/{sid}/message")
def messages(sid: str):
    return JSONResponse(final_messages(fake.scenarios.get(sid, "normal"), sid))


@app.delete("/session/{sid}")
def delete_session(sid: str):
    fake.deleted.append(sid)
    return True
