"""AIチャット(RAG)+ 履歴永続化 — /api/chat(docs/04 §6)。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import ChatMessage as ChatMsg
from models import ChatSession
from schemas import (
    ChatMessageOut,
    ChatRequest,
    ChatResponse,
    ChatSessionDetail,
    ChatSessionOut,
)
from services import opencode_client, telemetry, rag
from services.ontology_contract import agent_context

router = APIRouter(prefix="/api/chat", tags=["chat"])

_NO_BACKEND_MSG = "AIバックエンドが設定されていません(OPENCODE_URL / OPENROUTER_API_KEY)"

# OpenCode エージェント用 system prompt(MCPツールの使い分けを明示)
_OPENCODE_SYSTEM = """\
あなたは製造品質保証の専門AIアシスタントです。日本語で回答してください。

# データ
各報告書は defect_id(KZ25-XXXX)・発生日・\
客先・工程・機械・作業者・部品・加工数/不適合数・不具合内容・現象・原因・対策・4M分類・\
重要度(critical/high/medium/low)・状態(open/in_progress/completed)・費用を持つ。

# ツール選択の手順(defect-reports)
1. 質問に機械名・客先名などの固有名詞があれば、まず resolve_ontology_entity で
   正確な表記を確認する。別名の機械に勝手に読み替えない。
2. 条件別の件数・損失・CAPAはquery_quality_ontology。現象や作業者の絞り込みはlist_defect_reports。
   0件なら該当なしと伝える。ユーザー指定の条件を無断で外さない。
3. 内容が曖昧な類似事例探し(「〜のような不良」「同じ原因の事例」)→ search_defect_reports(意味検索)。
4. 個別の報告書の深掘り(全文・対策・費用)→ get_defect_report。
5. 条件別集計 → query_quality_ontology / 全体ダッシュボード → get_statistics / 統計的管理状態 → get_control_chart /
   いま注意すべき兆候 → get_active_alerts。
6. 同じツールを同じ引数で繰り返し呼ばない。多くの質問は2〜3回のツール呼び出しで足りる。

# 書き込み(要注意)
create_defect_report / update_defect_report は、ユーザーが「登録して」「更新して」「〜にして」と
明示的に依頼した場合のみ実行する。実行後は defect_id と変更内容を必ず報告する。
頼まれていない書き込みは絶対にしない。

# 回答規約
- 参照した報告書IDは必ず [KZ25-XXXX] 形式で引用する(画面ではリンクになる)。
- 冒頭に結論、その後に根拠(件数・該当例・傾向)。簡潔に、必要なら箇条書き。
- データに無いことは推測せず「データからは確認できない」と述べる。
- プロンプト内の「参考: 関連する不適合報告書」は事前検索の粗い候補にすぎない。
  質問に合わなければ無視し、ツールで正確なデータを引き直すこと。""" + "\n\n" + agent_context()


def chat_backend() -> str:
    """現在のチャットバックエンド種別を返す(チャットは OpenCode のみ)。"""
    return "opencode" if opencode_client.is_configured() else "none"


def _opencode_prompt(message: str, history: list[dict], context: str) -> str:
    """OpenCode は1問1答なので、履歴と文脈をプロンプトに畳み込む。"""
    lines = ["# 参考: 関連する不適合報告書", context, ""]
    if history:
        lines.append("# これまでの会話")
        for m in history[-20:]:
            role = "ユーザー" if m.get("role") == "user" else "アシスタント"
            lines.append(f"{role}: {m.get('content', '')}")
        lines.append("")
    lines.append(f"# 質問\n{message}")
    return "\n".join(lines)


def _build_context(db: Session, message: str) -> tuple[str, list[dict]]:
    """RAGは候補発見に使用。条件付き質問へ無条件の全体集計を混入させない。"""
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


# --- セッション永続化ヘルパー ---


def _get_or_create_session(db: Session, session_id: int | None, message: str) -> ChatSession:
    """session_id 指定時は既存を使い、無ければ新規作成(title=先頭30文字)。"""
    if session_id is not None:
        existing = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if existing:
            return existing
    title = (message or "").strip()[:30] or "新しい会話"
    session = ChatSession(title=title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _load_history(db: Session, session: ChatSession) -> list[dict]:
    """DB から直近20メッセージ(role/content)をロードする。"""
    msgs = (
        db.query(ChatMsg)
        .filter(ChatMsg.session_id == session.id)
        .order_by(ChatMsg.created_at.asc(), ChatMsg.id.asc())
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in msgs[-20:]]


def _save_user(db: Session, session: ChatSession, content: str) -> None:
    db.add(ChatMsg(session_id=session.id, role="user", content=content))
    session.updated_at = func.now()
    db.commit()


def _save_assistant(
    db: Session,
    session: ChatSession,
    content: str,
    sources: list | None,
    tools: list | None,
    thinking: str | None,
) -> None:
    db.add(
        ChatMsg(
            session_id=session.id,
            role="assistant",
            content=content,
            sources_json=json.dumps(sources, ensure_ascii=False) if sources else None,
            tools_json=json.dumps(tools, ensure_ascii=False) if tools else None,
            thinking=thinking or None,
        )
    )
    session.updated_at = func.now()
    db.commit()


def _message_out(m: ChatMsg) -> ChatMessageOut:
    return ChatMessageOut(
        id=m.id,
        role=m.role,
        content=m.content,
        sources=json.loads(m.sources_json) if m.sources_json else None,
        tools=json.loads(m.tools_json) if m.tools_json else None,
        thinking=m.thinking,
        created_at=m.created_at,
    )


# --- チャット本体 ---


@router.post("/stream")
def chat_stream(payload: ChatRequest):
    """SSE ストリーミングチャット。イベント: session / sources / tool / thinking / token / done / error。"""

    def generate():
        # 生成関数内で独立した DB セッションを使う(ストリーミング中も安全)
        db = SessionLocal()
        try:
            session = _get_or_create_session(db, payload.session_id, payload.message)
            # 最初に session イベント(sources より前)
            yield _sse("session", {"id": session.id, "title": session.title})

            # Langfuse トレース(未設定時は no-op)
            trace = telemetry.ChatTrace(payload.message, session.id)

            context, sources = _build_context(db, payload.message)
            source_items = _source_items(sources)
            trace.sources(source_items)
            yield _sse("sources", {"items": source_items})

            backend = chat_backend()
            # 履歴は現在の user メッセージ保存より前にロードする(二重計上を防ぐ)
            history = _load_history(db, session)
            _save_user(db, session, payload.message)  # error 時も user は残す

            if backend == "none":
                yield _sse("error", {"detail": _NO_BACKEND_MSG})
                return

            # イベントストリーミング: ツール実行(tool)・思考(thinking)・本文(token)を逐次転送
            content_parts: list[str] = []
            thinking_parts: list[str] = []
            tools_by_name: dict[str, dict] = {}
            for ev in opencode_client.stream(
                _OPENCODE_SYSTEM, _opencode_prompt(payload.message, history, context)
            ):
                yield _sse(ev["type"], {k: v for k, v in ev.items() if k != "type"})
                etype = ev.get("type")
                if etype == "token":
                    content_parts.append(ev.get("text", ""))
                elif etype == "thinking":
                    thinking_parts.append(ev.get("text", ""))
                elif etype == "tool":
                    name = ev.get("name")
                    tools_by_name[name] = {
                        "name": name,
                        "status": ev.get("status"),
                        "title": ev.get("title"),
                    }

            _save_assistant(
                db,
                session,
                "".join(content_parts),
                source_items,
                list(tools_by_name.values()) or None,
                "".join(thinking_parts) or None,
            )
            trace.finish("".join(content_parts), sorted(tools_by_name))
            # trace_id を渡し、画面の 👍/👎 を Langfuse スコアに紐づけられるようにする
            yield _sse("done", {"trace_id": trace.trace_id})
        except Exception as exc:  # noqa: BLE001 — 例外は error イベントで通知
            try:
                trace.finish("", [], error=str(exc))
            except NameError:
                pass  # trace 生成前の失敗
            yield _sse("error", {"detail": str(exc)})
        finally:
            db.close()

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    """非ストリーミング版(テスト用)。session_id 対応。"""
    context, sources = _build_context(db, payload.message)

    backend = chat_backend()
    if backend == "none":
        raise HTTPException(status_code=503, detail=_NO_BACKEND_MSG)

    session = _get_or_create_session(db, payload.session_id, payload.message)
    history = _load_history(db, session)
    _save_user(db, session, payload.message)

    answer = opencode_client.ask(
        _OPENCODE_SYSTEM, _opencode_prompt(payload.message, history, context)
    )
    source_items = _source_items(sources)
    _save_assistant(db, session, answer, source_items, None, None)

    return {"answer": answer, "sources": source_items, "session_id": session.id}


# --- 会話履歴の閲覧・削除 ---


@router.get("/sessions", response_model=list[ChatSessionOut])
def list_sessions(db: Session = Depends(get_db)):
    """会話セッション一覧(更新降順・message_count 付き)。"""
    counts = dict(
        db.query(ChatMsg.session_id, func.count(ChatMsg.id)).group_by(ChatMsg.session_id).all()
    )
    sessions = (
        db.query(ChatSession)
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        .all()
    )
    return [
        ChatSessionOut(
            id=s.id,
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
            message_count=counts.get(s.id, 0),
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(session_id: int, db: Session = Depends(get_db)):
    """セッション詳細(メタ + メッセージ列)。404 あり。"""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    msgs = (
        db.query(ChatMsg)
        .filter(ChatMsg.session_id == session_id)
        .order_by(ChatMsg.created_at.asc(), ChatMsg.id.asc())
        .all()
    )
    return ChatSessionDetail(
        session=ChatSessionOut(
            id=session.id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
            message_count=len(msgs),
        ),
        messages=[_message_out(m) for m in msgs],
    )


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: int, db: Session = Depends(get_db)):
    """セッション削除(メッセージも削除)。"""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    db.query(ChatMsg).filter(ChatMsg.session_id == session_id).delete(synchronize_session=False)
    db.delete(session)
    db.commit()
    return None
