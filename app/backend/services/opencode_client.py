"""OpenCode サーバー(ヘッドレス)経由のチャットバックエンド。

OpenCode(https://opencode.ai)を `opencode serve` で起動し、その HTTP API を
チャットの生成エンジンとして使う。モデルは OpenRouter 経由
(env: OPENCODE_PROVIDER / OPENCODE_MODEL)。

API(OpenCode server、OpenAPI /doc で確認済み):
- POST /session                          … セッション作成 → {"id": ...}
- POST /session/{sessionID}/message      … メッセージ送信(ブロッキング)
    body: {"model": {"providerID": ..., "modelID": ...}, "system": str,
           "tools": {ツール名: bool}, "parts": [{"type": "text", "text": ...}]}
    resp: {"info": {..., "error"?}, "parts": [{"type": "text", "text": ...}, ...]}
"""
from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger("defectreport.opencode")

OPENCODE_URL = os.getenv("OPENCODE_URL", "").rstrip("/")
# OPENCODE_MODEL が "provider/model" 形式ならプロバイダを自動判別する
# (例: "ollama/qwen3.8:27b-mtp-q4_K_M" → provider=ollama。
#  "anthropic/claude-sonnet-4.5" は openrouter 上のモデルIDなので分割しない)
_RAW_MODEL = os.getenv("OPENCODE_MODEL", "anthropic/claude-sonnet-4.5")
_KNOWN_PROVIDERS = ("ollama", "openrouter", "anthropic-direct")
if "/" in _RAW_MODEL and _RAW_MODEL.split("/", 1)[0] in _KNOWN_PROVIDERS:
    _prov, _model = _RAW_MODEL.split("/", 1)
else:
    _prov, _model = os.getenv("OPENCODE_PROVIDER", "openrouter"), _RAW_MODEL
PROVIDER = os.getenv("OPENCODE_PROVIDER", _prov)
MODEL = _model

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)


def is_configured() -> bool:
    """OPENCODE_URL が設定されていれば OpenCode バックエンドを使う。"""
    return bool(OPENCODE_URL)


def _extract_text(parts: list[dict]) -> str:
    """レスポンスの parts から text 部分を連結する(text/content 両対応)。"""
    chunks = []
    for p in parts or []:
        if p.get("type") == "text":
            chunks.append(p.get("text") or p.get("content") or "")
    return "".join(chunks).strip()


# チャット用途では OpenCode 標準のコーディング系ツールは使わない
# (MCP ツール defect-reports_* はそのまま有効)
_DISABLED_TOOLS = {
    name: False
    for name in ("bash", "edit", "write", "patch", "read", "glob", "grep", "list", "webfetch", "todowrite", "todoread", "task")
}

# 構造化抽出など「純粋な生成」では MCP ツールも含めて全ツールを無効化する
# OpenCodeはtoolsをpermissionルールに変換し、名前をWildcardで評価する。
# 固定リストだと追加されたOntology/CAPAツールが抽出用セッションに漏れる。
_ALL_TOOLS_OFF = {"*": False}


def _payload(system: str, prompt: str) -> dict:
    return {
        "model": {"providerID": PROVIDER, "modelID": MODEL},
        "system": system,
        "tools": dict(_DISABLED_TOOLS),
        "parts": [{"type": "text", "text": prompt}],
    }


def ask(system: str, prompt: str) -> str:
    """セッションを作成して1問1答する。失敗時は RuntimeError。"""
    if not is_configured():
        raise RuntimeError("OPENCODE_URL が設定されていません")

    with httpx.Client(base_url=OPENCODE_URL, timeout=_TIMEOUT) as client:
        r = client.post("/session", json={})
        r.raise_for_status()
        session_id = r.json()["id"]

        try:
            resp = client.post(f"/session/{session_id}/message", json=_payload(system, prompt))
            resp.raise_for_status()
            data = resp.json()
            # モデル呼び出し自体のエラーは info.error に入る(HTTP は 200)
            err = (data.get("info") or {}).get("error")
            if err:
                detail = (err.get("data") or {}).get("message") or err.get("name") or str(err)
                raise RuntimeError(f"OpenCode/モデルエラー: {detail[:300]}")
            text = _extract_text(data.get("parts", []))
            if not text:
                raise RuntimeError(f"OpenCode から空の応答: {str(data)[:200]}")
            return text
        finally:
            # 1問1答なのでセッションは使い捨てる(失敗しても無視)
            try:
                client.delete(f"/session/{session_id}")
            except httpx.HTTPError:
                pass


def _parse_json_text(text: str) -> dict:
    """応答テキストから最初の JSON オブジェクトを取り出してパースする。"""
    try:
        return json.loads(text)
    except ValueError:
        pass
    # ```json フェンスや前置きに包まれている場合: 最初の { から最後の } までを試す
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"JSON が見つかりません: {text[:200]}")


def ask_json(system: str, prompt: str, files: list[dict] | None = None) -> dict:
    """構造化抽出用の1問1答。応答を JSON としてパースして返す。

    files: [{"mime": str, "filename": str, "b64": str}](PDF/画像を message に添付)
    全ツール(コーディング系+MCP)を無効化し、純粋な生成として実行する。
    パース失敗時は「JSONのみで返答」と1回だけ再依頼する。
    """
    if not is_configured():
        raise RuntimeError("OPENCODE_URL が設定されていません")

    parts: list[dict] = [{"type": "text", "text": prompt}]
    for f in files or []:
        parts.append(
            {
                "type": "file",
                "mime": f["mime"],
                "filename": f.get("filename", "file"),
                "url": f"data:{f['mime']};base64,{f['b64']}",
            }
        )

    with httpx.Client(base_url=OPENCODE_URL, timeout=_TIMEOUT) as client:
        r = client.post("/session", json={})
        r.raise_for_status()
        session_id = r.json()["id"]

        def send(extra_note: str | None = None) -> str:
            body = {
                "model": {"providerID": PROVIDER, "modelID": MODEL},
                "system": system,
                "tools": dict(_ALL_TOOLS_OFF),
                "parts": (parts + [{"type": "text", "text": extra_note}]) if extra_note else parts,
            }
            resp = client.post(f"/session/{session_id}/message", json=body)
            resp.raise_for_status()
            data = resp.json()
            err = (data.get("info") or {}).get("error")
            if err:
                detail = (err.get("data") or {}).get("message") or err.get("name") or str(err)
                raise RuntimeError(f"OpenCode/モデルエラー: {detail[:300]}")
            return _extract_text(data.get("parts", []))

        try:
            text = send()
            try:
                return _parse_json_text(text)
            except ValueError:
                # 1回だけ再依頼(前置きなしの JSON のみを要求)
                text = send("前置きや説明を付けず、指示した JSON オブジェクトのみを返してください。")
                return _parse_json_text(text)
        finally:
            try:
                client.delete(f"/session/{session_id}")
            except httpx.HTTPError:
                pass


def stream(system: str, prompt: str):
    """イベントストリーミング版: ツール実行・思考・本文を逐次 yield する。

    yield する dict:
      {"type": "tool", "name": str, "status": "pending|running|completed|error", "title": str|None}
      {"type": "thinking", "text": str}   … 推論テキストのデルタ
      {"type": "token", "text": str}      … 回答本文のデルタ
    終了条件: session.idle。モデルエラーは RuntimeError。

    仕組み: GET /event(SSEバス)を購読してから POST /session/{id}/prompt_async。
    message.part.delta(field=text)を partID の種別(text/reasoning)で振り分ける。
    """
    if not is_configured():
        raise RuntimeError("OPENCODE_URL が設定されていません")

    with httpx.Client(base_url=OPENCODE_URL, timeout=httpx.Timeout(300.0, connect=10.0, read=300.0)) as client:
        r = client.post("/session", json={})
        r.raise_for_status()
        session_id = r.json()["id"]

        part_types: dict[str, str] = {}      # partID → part type
        tool_status: dict[str, str] = {}     # callID → 最終通知済み status
        got_text = False

        try:
            with client.stream("GET", "/event") as es:
                # 購読が開いてからプロンプト送信(イベントの取りこぼし防止)
                body = _payload(system, prompt)
                pr = client.post(f"/session/{session_id}/prompt_async", json=body)
                pr.raise_for_status()

                for line in es.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        ev = json.loads(line[5:].strip())
                    except ValueError:
                        continue
                    etype = ev.get("type")
                    props = ev.get("properties") or {}
                    if props.get("sessionID") != session_id:
                        continue

                    if etype == "message.part.updated":
                        part = props.get("part") or {}
                        ptype = part.get("type")
                        if part.get("id"):
                            part_types[part["id"]] = ptype
                        if ptype == "tool":
                            call_id = part.get("callID") or part.get("id")
                            status = (part.get("state") or {}).get("status")
                            if status and tool_status.get(call_id) != status:
                                tool_status[call_id] = status
                                yield {
                                    "type": "tool",
                                    "name": part.get("tool"),
                                    "status": status,
                                    "title": (part.get("state") or {}).get("title"),
                                }

                    elif etype == "message.part.delta":
                        if props.get("field") != "text":
                            continue
                        delta = props.get("delta") or ""
                        if not delta:
                            continue
                        ptype = part_types.get(props.get("partID"), "text")
                        if ptype == "reasoning":
                            yield {"type": "thinking", "text": delta}
                        else:
                            got_text = True
                            yield {"type": "token", "text": delta}

                    elif etype == "message.updated":
                        info = (props.get("info") or {})
                        err = info.get("error")
                        if err and info.get("role") == "assistant":
                            detail = (err.get("data") or {}).get("message") or err.get("name") or str(err)
                            raise RuntimeError(f"OpenCode/モデルエラー: {detail[:300]}")

                    elif etype in ("session.error",):
                        detail = json.dumps(props.get("error") or props, ensure_ascii=False)
                        raise RuntimeError(f"OpenCodeセッションエラー: {detail[:300]}")

                    elif etype == "session.idle":
                        break

            if not got_text:
                # デルタが取れなかった場合の保険: 完了メッセージから全文を回収
                msgs = client.get(f"/session/{session_id}/message").json()
                for m in reversed(msgs if isinstance(msgs, list) else []):
                    info = m.get("info") or {}
                    if info.get("role") == "assistant":
                        text = _extract_text(m.get("parts", []))
                        if text:
                            got_text = True
                            yield {"type": "token", "text": text}
                            break
            if not got_text:
                # それでも空なら静かに成功扱いにせず、明示的に失敗させる
                # (呼び出し側でエラーイベントになり、利用者・評価側がリトライできる)
                raise RuntimeError("OpenCodeが空応答を返しました(モデル未応答)。もう一度お試しください")
        finally:
            try:
                client.delete(f"/session/{session_id}")
            except httpx.HTTPError:
                pass


def health() -> bool:
    """OpenCode サーバーの疎通確認。"""
    if not is_configured():
        return False
    try:
        with httpx.Client(base_url=OPENCODE_URL, timeout=5.0) as client:
            r = client.get("/global/health")
            if r.status_code == 404:
                r = client.get("/app")  # 旧バージョン互換
            return r.status_code < 500
    except httpx.HTTPError:
        return False
