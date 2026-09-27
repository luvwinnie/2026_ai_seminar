"""Anthropic Claude API ラッパー。

利用規約(docs/04 §7):
- モデルは env `ANTHROPIC_MODEL`(既定 `claude-sonnet-5`)。
- temperature / top_p / top_k / budget_tokens は送らない(Sonnet 5 では 400)。
- thinking はフィールド省略(既定 adaptive)。
- 構造化抽出は output_config={"format": {"type": "json_schema", "schema": ...}}。
- チャットは client.messages.stream(...) + text_stream。
- ANTHROPIC_API_KEY 未設定時は is_configured() が False を返す(呼び出し側で 503)。
"""
from __future__ import annotations

import base64
import json
import os
from collections.abc import Iterator

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

_client = None


class LLMNotConfigured(RuntimeError):
    """ANTHROPIC_API_KEY 未設定。"""


def is_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _get_client():
    global _client
    if not is_configured():
        raise LLMNotConfigured("ANTHROPIC_API_KEY が設定されていません")
    if _client is None:
        import anthropic  # 遅延 import

        _client = anthropic.Anthropic()
    return _client


# 抽出対象フィールドの JSON スキーマ(report フィールドのサブセット)。
# 不明値は null を許容するため各型に "null" を含める。
def _extraction_schema() -> dict:
    def s(*types):
        return {"type": [*types, "null"]}

    props = {
        "occurrence_date": s("string"),
        "report_date": s("string"),
        "customer": s("string"),
        "discoverer": s("string"),
        "process": s("string"),
        "machine_name": s("string"),
        "operator_name": s("string"),
        "part_number": s("string"),
        "part_name": s("string"),
        "production_count": s("integer"),
        "defect_count": s("integer"),
        "defect_description": s("string"),
        "good_condition": s("string"),
        "phenomenon": s("string"),
        "cause": s("string"),
        "factor": s("string"),
        "severity": s("string"),
        "countermeasure": s("string"),
        "material_cost": s("number"),
        "processing_cost": s("number"),
        "outsourcing_cost": s("number"),
        "other_cost": s("number"),
        "is_recurrence": s("boolean"),
        "has_procedure": s("boolean"),
        "notes": s("string"),
    }
    return {
        "type": "object",
        "properties": props,
        "required": list(props.keys()),
        "additionalProperties": False,
    }


_EXTRACT_INSTRUCTION = (
    "あなたは製造業の不適合報告書を読み取る専門AIです。"
    "添付の帳票(画像/PDF)から各項目を抽出し、指定のJSONスキーマで返してください。"
    "日付は YYYY-MM-DD 形式。読み取れない項目は null にしてください。"
    "severity は critical/high/medium/low のいずれかに正規化してください。"
)


def _first_json(message) -> dict:
    """レスポンスの最初の text ブロックを JSON としてパースする。"""
    for block in message.content:
        if block.type == "text":
            return json.loads(block.text)
    return {}


def extract_from_document(file_bytes: bytes, media_type: str, filename: str) -> dict:
    """画像/PDF から構造化抽出する(Claude vision + structured outputs)。"""
    client = _get_client()
    b64 = base64.standard_b64encode(file_bytes).decode("utf-8")

    if media_type == "application/pdf":
        source_block = {
            "type": "document",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        }
    else:
        source_block = {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        }

    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [source_block, {"type": "text", "text": _EXTRACT_INSTRUCTION}],
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": _extraction_schema()}},
    )
    return _first_json(message)


def normalize_cells(cell_dump: str) -> dict:
    """xlsx のセルダンプを Claude で構造化補正する(API キーがある場合のみ呼ぶ)。"""
    client = _get_client()
    instruction = (
        "以下は不適合報告書 Excel から抽出したラベルと値の一覧です。"
        "指定のJSONスキーマに正規化してください。読み取れない項目は null。\n\n"
        f"{cell_dump}"
    )
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": instruction}],
        output_config={"format": {"type": "json_schema", "schema": _extraction_schema()}},
    )
    return _first_json(message)


def _analysis_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "category_4m": {"type": "string", "enum": ["Man", "Machine", "Material", "Method"]},
            "factor": {"type": "string"},
            "reasoning": {"type": "string"},
            "improvements": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["category_4m", "factor", "reasoning", "improvements"],
        "additionalProperties": False,
    }


def analyze_4m(report_text: str) -> dict:
    """4M 分類 + 改善提案(structured outputs)。"""
    client = _get_client()
    instruction = (
        "あなたは製造品質保証の専門AIです。以下の不適合報告書を 4M(Man/Machine/Material/Method)"
        "の観点で分類し、根本原因の要因と具体的な改善提案を提示してください。\n\n"
        f"{report_text}"
    )
    message = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": instruction}],
        output_config={"format": {"type": "json_schema", "schema": _analysis_schema()}},
    )
    return _first_json(message)


_CHAT_SYSTEM = (
    "あなたは製造品質保証の専門AIアシスタントです。"
    "提示された文脈の報告書に基づいて回答し、参照した報告書IDを [KZ25-XXXX] 形式で引用してください。"
    "文脈に無い情報は推測せず、分からない場合はその旨を述べてください。"
)


def _build_messages(message: str, history: list[dict], context: str) -> list[dict]:
    """履歴 + 文脈付きのユーザメッセージを組み立てる。"""
    msgs: list[dict] = []
    for h in history[-10:]:  # 直近10往復まで
        role = h.get("role")
        if role in ("user", "assistant"):
            msgs.append({"role": role, "content": h.get("content", "")})
    user_content = f"# 参考となる報告書\n{context}\n\n# 質問\n{message}"
    msgs.append({"role": "user", "content": user_content})
    return msgs


def chat_stream(message: str, history: list[dict], context: str) -> Iterator[str]:
    """ストリーミングチャット(トークンを逐次 yield)。"""
    client = _get_client()
    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        system=_CHAT_SYSTEM,
        messages=_build_messages(message, history, context),
    ) as stream:
        for text in stream.text_stream:
            yield text


def chat(message: str, history: list[dict], context: str) -> str:
    """非ストリーミングチャット(テスト用)。"""
    client = _get_client()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=_CHAT_SYSTEM,
        messages=_build_messages(message, history, context),
    )
    parts = [b.text for b in resp.content if b.type == "text"]
    return "".join(parts)
