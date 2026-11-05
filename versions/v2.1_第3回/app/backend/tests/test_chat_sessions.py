"""会話の保存・一覧・復元・削除（04_API設計書.md §6.3、07_試験・運用仕様書.md AC-v20-04）。"""

from sqlalchemy import func, select, text

from database import SessionLocal
from models import ChatMessage, ChatSession, utcnow


def make_session(title: str, contents: list[str]) -> int:
    with SessionLocal() as db:
        session = ChatSession(title=title)
        db.add(session)
        db.flush()
        for i, content in enumerate(contents):
            db.add(ChatMessage(session_id=session.id, role="user" if i % 2 == 0 else "assistant", content=content,
                               tools_json='[{"name": "defect-reports_get_defect_report", "status": "completed", "title": "KZ25-0043"}]' if i % 2 else None,
                               thinking="考え中" if i % 2 else None))
        db.commit()
        return session.id


def test_AC_v20_04_sessions_newest_first(client):
    first = make_session("会話A", ["質問A", "回答A"])
    second = make_session("会話B", ["質問B"])
    with SessionLocal() as db:  # 会話A に発言を足した → A が新しい
        db.get(ChatSession, first).updated_at = utcnow()
        db.commit()
    sessions = client.get("/api/chat/sessions").json()
    ids = [s["id"] for s in sessions]
    assert ids.index(first) < ids.index(second)
    row = next(s for s in sessions if s["id"] == first)
    assert set(row) == {"id", "title", "created_at", "updated_at", "message_count"}
    assert row["title"] == "会話A" and row["message_count"] == 2
    assert row["updated_at"].endswith("Z") or row["updated_at"].endswith("+00:00")  # UTC と分かる形


def test_AC_v20_04_restore_session(client):
    session_id = make_session("会話C", ["KZ25-0043 の内容を教えて", "KZ25-0043 は a61nx …"])
    body = client.get(f"/api/chat/sessions/{session_id}").json()
    assert body["session"]["id"] == session_id
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert set(body["messages"][1]) == {"id", "role", "content", "tools", "thinking", "created_at"}
    # 保存した道具の記録と思考も戻す
    assert body["messages"][1]["tools"] == [{"name": "defect-reports_get_defect_report", "status": "completed", "title": "KZ25-0043"}]
    assert body["messages"][1]["thinking"] == "考え中"
    assert body["messages"][0]["tools"] is None


def test_AC_v20_04_not_found(client):
    assert client.get("/api/chat/sessions/999999").status_code == 404
    assert client.get("/api/chat/sessions/999999").json() == {"detail": "会話が見つかりません"}
    assert client.delete("/api/chat/sessions/999999").status_code == 404


def test_AC_v20_04_delete_session(client):
    session_id = make_session("会話D", ["質問", "回答"])
    response = client.delete(f"/api/chat/sessions/{session_id}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/api/chat/sessions/{session_id}").status_code == 404
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == session_id)) == 0


def test_AC_v20_04_delete_cascades_in_db(client):
    # DB の外部キー（ON DELETE CASCADE）でも発言が消える
    session_id = make_session("会話E", ["質問", "回答"])
    with SessionLocal() as db:
        db.execute(text("DELETE FROM chat_sessions WHERE id = :id"), {"id": session_id})
        db.commit()
        assert db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == session_id)) == 0
