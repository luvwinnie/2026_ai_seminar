"""AI アシスタント（04_API設計書.md §6、06_AI設計書.md §1）。

会話の正本は DB（chat_sessions・chat_messages）。履歴はサーバーが DB から直近20件を読み、OpenCode に1つの本文で渡す。
"""

import json
import os
from collections.abc import AsyncIterator
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import ChatMessage, ChatSession, utcnow
from schemas import ChatAnswer, ChatRequest, ChatSessionDetail, ChatSessionOut
from services import telemetry
from services.opencode_client import EMPTY_RESPONSE, OpenCodeClient, OpenCodeError

router = APIRouter(prefix="/api/chat")

NO_BACKEND = "AIバックエンドが設定されていません(OPENCODE_URL / OPENROUTER_API_KEY)"
NOT_FOUND = "会話が見つかりません"
HISTORY_LIMIT = 20
TITLE_LENGTH = 30

# 毎回の要求に付ける指示（06_AI設計書.md §1.4）。AGENTS.md・MCP の instructions と同じ決まりを書く（§3.1）
_OPENCODE_SYSTEM = """\
あなたは製造業の品質保証を手伝う「DefectReport AI」のアシスタントです。日本語で答えます。

## データ
- 不適合報告書（KZ25-0001〜KZ25-0110 の110件、架空のデータ）。項目は defect_id（報告書番号）・発生日・客先・工程・機械・作業者・部品・加工数と不適合数・不具合内容・現象・原因・対策・4M・重要度・状態・費用。
- 「件」は報告書の数、「個」は加工数・不適合数の合計。期間は発生日で数え、両端の日を含む。
- 報告書のデータには、MCP の道具（defect-reports_ で始まる道具）でだけ触れる。

## 道具の選び方
- 機械・工程・客先などの名前は、まず list_masters で正しい表記を確かめる。似た名前の別のものに読み替えない。
- 名前は一字一句そのまま使う。list_masters に無い名前は「該当は存在しません」と答える。1文字でも違う名前（例：GENOS M560-V と GENOS M660-V）は別のもので、読み替えて別のものの件数や内容を答えない。似た名前は「もしかして」と候補に挙げるだけにする。
- 条件がはっきりしていれば list_defect_reports（完全一致）、内容があいまいなら search_defect_reports。
- 1件の中身は get_defect_report。件数・集計は、名前を確かめたあとでも必ず get_statistics か list_defect_reports の total で数える（search_defect_reports の結果の数や、list_masters の usage_count で件数を答えない。list_masters は表記を確かめるためだけに使う）。
- 同じ道具を同じ引数で繰り返し呼ばない（多くは2〜3回で足りる）。

## 書き込み・画面の操作
- この版の道具は読み取りだけ。報告書の登録・更新や、画面の操作（画面を開く・移る・テーマを変える）を頼まれたら、「この版ではできません」と答える。実行していない操作を「しました」と言わない。
- 報告書を画面で開くよう頼まれたら、「この版ではできません」に続けて、その報告書番号を [KZ25-XXXX] の形で書き、「リンクから開けます」と案内する（番号は利用者が書いたとおり。中身は道具で取ってから述べる）。

## 回答の決まり
- 毎ターン独立：報告書の値・件数・内容を言うときは、そのターンで道具を呼んで得た結果だけを使う。前のターンの結果や会話の履歴から組み立て直さない。道具を1回も呼ばずに報告書の中身を語らない。
- 存在しない報告書番号や機械名を作らない。道具が error や0件を返したら、「見つかりません」「該当は存在しません」「0件です」と答え、成功のように言わない。利用者の条件を黙って外さない。
- 結論を先に、根拠（件数・例・傾向）を後に書く。報告書は [KZ25-XXXX] の形で示す。データに無いことは「データからは確認できない」と言う。
"""


def chat_backend() -> str:
    """チャットの AI の有無（/health の chat_backend）。"""
    return "opencode" if os.environ.get("OPENCODE_URL") else "none"


def model_ref() -> tuple[str, str]:
    """OPENCODE_MODEL からプロバイダとモデルを決める。ollama/ で始まれば接続先は ollama。"""
    model = os.environ.get("OPENCODE_MODEL", "anthropic/claude-sonnet-4.5")
    if model.startswith("ollama/"):
        return "ollama", model.removeprefix("ollama/")
    return os.environ.get("OPENCODE_PROVIDER", "openrouter"), model


def make_client() -> OpenCodeClient:
    """OpenCode のクライアント。試験ではこれを差し替える。"""
    return OpenCodeClient(os.environ["OPENCODE_URL"])


def build_prompt(history: list[ChatMessage], question: str) -> str:
    """OpenCode は1問1答なので、履歴と質問を1つの本文に畳み込む（06_AI設計書.md §1.4）。"""
    lines = []
    if history:
        lines.append("# これまでの会話")
        for message in history:
            speaker = "ユーザー" if message.role == "user" else "アシスタント"
            lines.append(f"{speaker}: {message.content}")
        lines.append("")
    lines.append("# 質問")
    lines.append(question)
    return "\n".join(lines)


def _start_turn(message: str, session_id: int | None) -> tuple[dict, str]:
    """会話を読むか作り、直近20件を読んでから質問を保存する。(session の中身, プロンプト) を返す。"""
    with SessionLocal() as db:
        session = db.get(ChatSession, session_id) if session_id else None
        if session is None:
            session = ChatSession(title=message.strip()[:TITLE_LENGTH] or "新しい会話")
            db.add(session)
            db.flush()
        # 履歴は今の質問を保存する前に読む（二重に数えない）
        history = list(reversed(db.scalars(
            select(ChatMessage).where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(HISTORY_LIMIT)
        ).all()))
        prompt = build_prompt(history, message)
        db.add(ChatMessage(session_id=session.id, role="user", content=message))
        session.updated_at = utcnow()
        db.commit()
        return {"id": session.id, "title": session.title}, prompt


def _save_answer(session_id: int, content: str, tools: list[dict], thinking: str) -> None:
    with SessionLocal() as db:
        db.add(ChatMessage(
            session_id=session_id, role="assistant", content=content,
            tools_json=json.dumps(tools, ensure_ascii=False), thinking=thinking or None,
        ))
        db.get(ChatSession, session_id).updated_at = utcnow()
        db.commit()


async def run_chat(message: str, session_id: int | None) -> AsyncIterator[tuple[str, dict]]:
    """1問を処理し、(イベント名, data) を順に返す：session → thinking・tool・token → done か error。"""
    session, prompt = _start_turn(message, session_id)
    yield "session", session
    if chat_backend() == "none":
        yield "error", {"detail": NO_BACKEND}
        return

    trace_id = telemetry.start_trace(message)
    answer, thinking, tools = [], [], {}
    provider_id, model_id = model_ref()
    try:
        async for kind, data in make_client().stream(prompt, _OPENCODE_SYSTEM, provider_id, model_id):
            if kind == "token":
                answer.append(data["text"])
            elif kind == "thinking":
                thinking.append(data["text"])
            elif kind == "tool":
                tools[data["name"]] = data  # 名前ごとの最後の状態
            yield kind, data
        if not "".join(answer).strip():
            raise OpenCodeError(EMPTY_RESPONSE)
    except OpenCodeError as e:
        yield "error", {"detail": str(e)}
        return
    except Exception as e:  # 通信の失敗など。SSE を始めたあとなので HTTP の状態は 200 のまま
        yield "error", {"detail": f"OpenCode との通信に失敗しました: {type(e).__name__}: {e}"}
        return
    # 失敗した回答は保存しない（質問は保存済み）
    _save_answer(session["id"], "".join(answer), list(tools.values()), "".join(thinking))
    yield "done", {"trace_id": trace_id}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def chat_stream(body: ChatRequest):
    async def events():
        async for event, data in run_chat(body.message, body.session_id):
            yield _sse(event, data)

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("", response_model=ChatAnswer)
async def chat(body: ChatRequest):
    """回答をまとめて返す（試験用、04_API設計書.md §6.4）。"""
    answer, session_id = [], None
    async for event, data in run_chat(body.message, body.session_id):
        if event == "session":
            session_id = data["id"]
        elif event == "token":
            answer.append(data["text"])
        elif event == "error":
            raise HTTPException(status_code=503 if data["detail"] == NO_BACKEND else 502, detail=data["detail"])
    return {"answer": "".join(answer), "session_id": session_id}


def _session_out(db: Session, session: ChatSession) -> dict:
    count = db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == session.id))
    return {
        "id": session.id, "title": session.title, "created_at": session.created_at,
        "updated_at": session.updated_at, "message_count": count,
    }


@router.get("/sessions", response_model=list[ChatSessionOut])
def list_sessions(db: Session = Depends(get_db)):
    sessions = db.scalars(select(ChatSession).order_by(ChatSession.updated_at.desc(), ChatSession.id.desc()))
    return [_session_out(db, s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    messages = db.scalars(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at, ChatMessage.id)
    )
    return {
        "session": _session_out(db, session),
        "messages": [
            {
                "id": m.id, "role": m.role, "content": m.content,
                "tools": json.loads(m.tools_json) if m.tools_json else None,
                "thinking": m.thinking, "created_at": m.created_at,
            }
            for m in messages
        ],
    }


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: int, db: Session = Depends(get_db)):
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    db.delete(session)  # 発言も消える
    db.commit()
    return Response(status_code=204)
