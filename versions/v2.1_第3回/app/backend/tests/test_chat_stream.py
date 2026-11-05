"""チャット API を、OpenCode を差し替えて確かめる（LLM を呼ばない。07_試験・運用仕様書.md §2.3・§2.4）。"""

import json

import pytest

from database import SessionLocal
from models import ChatMessage, ChatSession
from routers import chat
from services.opencode_client import BUILTIN_TOOLS, EMPTY_RESPONSE, OpenCodeClient
from tests.fake_opencode import ANSWER, THINKING, TOOL, FakeOpenCode

NO_BACKEND = "AIバックエンドが設定されていません(OPENCODE_URL / OPENROUTER_API_KEY)"


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def ask(client, message: str, session_id: int | None = None, **extra) -> list[tuple[str, dict]]:
    response = client.post("/api/chat/stream", json={"message": message, "session_id": session_id, **extra})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_sse(response.text)


def names(events) -> list[str]:
    return [name for name, _ in events]


def text_of(events, kind: str = "token") -> str:
    return "".join(data["text"] for name, data in events if name == kind)


def messages_of(client, session_id: int) -> list[dict]:
    return client.get(f"/api/chat/sessions/{session_id}").json()["messages"]


@pytest.fixture
def fake(monkeypatch):
    fake = FakeOpenCode()
    monkeypatch.setenv("OPENCODE_URL", "http://fake-opencode")
    monkeypatch.setenv("OPENCODE_MODEL", "ollama/gemma4:26b")
    monkeypatch.setattr(chat, "make_client", lambda: OpenCodeClient("http://fake-opencode", transport=fake.transport))
    return fake


def test_AC_v20_07_event_order(client, fake):
    events = ask(client, "KZ25-0043 の内容を教えて")
    # 先頭は session、最後は done か error のどちらか1つ
    assert events[0][0] == "session"
    assert set(events[0][1]) == {"id", "title"}
    assert names(events)[-1] == "done"
    assert sum(name in ("done", "error") for name in names(events)) == 1
    assert {"thinking", "tool", "token"} <= set(names(events))
    # 道具は状態が変わったときだけ（pending → running → completed）
    tools = [data for name, data in events if name == "tool"]
    assert tools == [
        {"name": TOOL, "status": "pending", "title": None},
        {"name": TOOL, "status": "running", "title": None},
        {"name": TOOL, "status": "completed", "title": "KZ25-0043"},
    ]
    # ほかのセッションの本文・送った質問は混ざらず、差分と part の全文を二重に送らない
    assert text_of(events) == ANSWER
    assert text_of(events, "thinking") == THINKING


def test_AC_v20_07_request_to_opencode(client, fake):
    ask(client, "KZ25-0043 の内容を教えて")
    body = fake.prompts[-1]
    assert body["model"] == {"providerID": "ollama", "modelID": "gemma4:26b"}
    assert body["tools"] == {name: False for name in BUILTIN_TOOLS}  # 元からある道具は切る
    assert body["tools"]["question"] is False
    assert "list_masters" in body["system"]
    assert body["parts"][0]["text"].endswith("# 質問\nKZ25-0043 の内容を教えて")
    # 1問ごとに OpenCode のセッションを作って消す
    assert fake.deleted == fake.created == [body["session"]]


def test_AC_v20_01_answer_is_saved(client, fake):
    events = ask(client, "KZ25-0043 の内容を教えて")
    messages = messages_of(client, events[0][1]["id"])
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "KZ25-0043 の内容を教えて"
    assert messages[1]["content"] == ANSWER
    assert messages[1]["tools"] == [{"name": TOOL, "status": "completed", "title": "KZ25-0043"}]
    assert messages[1]["thinking"] == THINKING


def test_AC_v20_07_fallback_to_final_message(client, fake):
    # 逐次の差分が無いときは、完了した回答を取り直して token を1回送る
    events = ask(client, "差分なしで答えて")
    assert [data for name, data in events if name == "token"] == [{"text": ANSWER}]
    assert names(events)[-1] == "done"


def test_AC_v20_08_no_backend(client):
    events = ask(client, "KZ25-0043 の内容を教えて")
    assert names(events) == ["session", "error"]
    assert events[1][1] == {"detail": NO_BACKEND}
    # 質問は保存する
    assert [m["role"] for m in messages_of(client, events[0][1]["id"])] == ["user"]
    response = client.post("/api/chat", json={"message": "テスト", "session_id": None})
    assert response.status_code == 503
    assert response.json() == {"detail": NO_BACKEND}
    assert client.get("/health").json()["chat_backend"] == "none"
    assert client.get("/api/reports").json()["total"] == 110


def test_AC_v20_08_health_with_backend(client, fake):
    assert client.get("/health").json()["chat_backend"] == "opencode"


def test_AC_v20_04_history_is_read_from_db(client, fake):
    with SessionLocal() as db:
        session = ChatSession(title="履歴の試験")
        db.add(session)
        db.flush()
        for i in range(25):
            db.add(ChatMessage(session_id=session.id, role="user" if i % 2 == 0 else "assistant", content=f"発言{i:02d}"))
        db.commit()
        session_id = session.id
    # 画面が history を送っても使わない
    ask(client, "今の質問", session_id, history=[{"role": "user", "content": "画面から送った履歴"}])
    prompt = fake.prompts[-1]["parts"][0]["text"]
    assert "画面から送った履歴" not in prompt
    # 直近20件（発言05〜24）だけ。今の質問は1回だけ入る
    assert "発言04" not in prompt
    assert all(f"発言{i:02d}" in prompt for i in range(5, 25))
    assert prompt.count("今の質問") == 1
    assert prompt.index("ユーザー: 発言24") < prompt.index("# 質問\n今の質問")
    assert len(messages_of(client, session_id)) == 27


def test_AC_v20_04_new_session_title(client, fake):
    question = "汎用フライスのバリ残りは何件ありますか？これまでの対策も教えてください。"
    events = ask(client, question, session_id=999999)  # 無い会話なら新しく作る
    assert events[0][1]["title"] == question[:30]
    assert events[0][1]["id"] != 999999


def test_AC_v21_02_empty_response_is_error(client, fake):
    events = ask(client, "空応答の試験")
    assert names(events) == ["session", "error"]
    assert events[-1][1] == {"detail": EMPTY_RESPONSE}
    # 回答は保存しない（質問は残す）
    assert [m["role"] for m in messages_of(client, events[0][1]["id"])] == ["user"]


def test_AC_v21_03_model_error_is_error(client, fake):
    events = ask(client, "402 の試験")
    assert names(events)[-1] == "error"
    assert "done" not in names(events)
    detail = events[-1][1]["detail"]
    assert detail.startswith("OpenCode/モデルエラー:")
    assert "Insufficient credits" in detail and "402" in detail
    assert [m["role"] for m in messages_of(client, events[0][1]["id"])] == ["user"]


def test_AC_v21_03_session_error_is_error(client, fake):
    events = ask(client, "セッションエラーの試験")
    assert events[-1] == ("error", {"detail": "OpenCode/モデルエラー: 接続できません"})


def test_AC_v21_04_length_is_error(client, fake):
    events = ask(client, "出力の上限の試験")
    assert names(events)[-1] == "error"
    assert "done" not in names(events)
    assert "finish=length" in events[-1][1]["detail"]
    # 途中までの本文は届いても、回答として保存しない
    assert [m["role"] for m in messages_of(client, events[0][1]["id"])] == ["user"]


def test_AC_v20_07_connection_failure_is_error(client, monkeypatch):
    monkeypatch.setenv("OPENCODE_URL", "http://127.0.0.1:9")  # 誰も待っていないポート
    events = ask(client, "KZ25-0043 の内容を教えて")
    assert names(events) == ["session", "error"]
    assert events[-1][1]["detail"].startswith("OpenCode との通信に失敗しました")


def test_AC_v20_16_no_langfuse_trace_id_null(client, fake, monkeypatch):
    for key in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    events = ask(client, "KZ25-0043 の内容を教えて")
    assert events[-1] == ("done", {"trace_id": None})


def test_AC_v20_07_non_streaming_chat(client, fake):
    response = client.post("/api/chat", json={"message": "KZ25-0043 の内容を教えて", "session_id": None})
    assert response.status_code == 200
    assert response.json()["answer"] == ANSWER
    response = client.post("/api/chat", json={"message": "402 の試験", "session_id": None})
    assert response.status_code == 502
    assert response.json()["detail"].startswith("OpenCode/モデルエラー:")
