"""帳票AI抽出・4M分析のバックエンド。

優先: OpenCode(OpenRouter 経由、services/opencode_client.ask_json)
代替: Anthropic API 直叩き(ANTHROPIC_API_KEY がある場合)
どちらも無ければ LLMNotConfigured(呼び出し側で 503)。

チャットは routers/chat.py が OpenCode を直接使う(本モジュールは関与しない)。

Anthropic 経路の利用規約(docs/04 §7):
- モデルは env `ANTHROPIC_MODEL`(既定 `claude-sonnet-5`)。
- temperature / top_p / top_k / budget_tokens は送らない(Sonnet 5 では 400)。
- 構造化抽出は output_config={"format": {"type": "json_schema", "schema": ...}}。
"""
from __future__ import annotations

import base64
import json
import os

from services import opencode_client

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

_client = None

_4M_VALUES = ("Man", "Machine", "Material", "Method")


class LLMNotConfigured(RuntimeError):
    """AIバックエンド未設定。"""


def ai_backend() -> str:
    """抽出・4M分析に使うバックエンド種別。"""
    if opencode_client.is_configured():
        return "opencode"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "none"


def is_configured() -> bool:
    return ai_backend() != "none"


def _get_client():
    global _client
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise LLMNotConfigured("AIバックエンドが設定されていません(OPENCODE_URL / OPENROUTER_API_KEY)")
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


def _schema_prompt(schema: dict) -> str:
    """OpenCode 経路用: スキーマをプロンプト内に埋め込む。"""
    return (
        "次の JSON スキーマに厳密に従った JSON オブジェクト**のみ**を返してください"
        "(前置き・説明・コードフェンス不要):\n" + json.dumps(schema, ensure_ascii=False)
    )


def _first_json(message) -> dict:
    """Anthropic レスポンスの最初の text ブロックを JSON としてパースする。"""
    for block in message.content:
        if block.type == "text":
            return json.loads(block.text)
    return {}


def extract_from_document(file_bytes: bytes, media_type: str, filename: str) -> dict:
    """画像/PDF から構造化抽出する(vision + 構造化出力)。"""
    backend = ai_backend()
    if backend == "none":
        raise LLMNotConfigured("AIバックエンドが設定されていません(OPENCODE_URL / OPENROUTER_API_KEY)")

    b64 = base64.standard_b64encode(file_bytes).decode("utf-8")

    if backend == "opencode":
        return opencode_client.ask_json(
            system=_EXTRACT_INSTRUCTION,
            prompt=_schema_prompt(_extraction_schema()),
            files=[{"mime": media_type, "filename": filename, "b64": b64}],
        )

    # Anthropic 経路
    client = _get_client()
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
    """xlsx のセルダンプを構造化補正する(AIバックエンドがある場合のみ呼ぶ)。"""
    backend = ai_backend()
    if backend == "none":
        raise LLMNotConfigured("AIバックエンドが設定されていません(OPENCODE_URL / OPENROUTER_API_KEY)")

    instruction = (
        "以下は不適合報告書 Excel から抽出したラベルと値の一覧です。"
        "指定のJSONスキーマに正規化してください。読み取れない項目は null。\n\n"
        f"{cell_dump}"
    )

    if backend == "opencode":
        return opencode_client.ask_json(
            system="あなたは製造業の不適合報告書を読み取る専門AIです。",
            prompt=f"{instruction}\n\n{_schema_prompt(_extraction_schema())}",
        )

    client = _get_client()
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
            "category_4m": {"type": "string", "enum": list(_4M_VALUES)},
            "factor": {"type": "string"},
            "reasoning": {"type": "string"},
            "improvements": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["category_4m", "factor", "reasoning", "improvements"],
        "additionalProperties": False,
    }


def analyze_4m(report_text: str) -> dict:
    """4M 分類 + 改善提案(構造化出力)。category_4m は4値に検証する。"""
    backend = ai_backend()
    if backend == "none":
        raise LLMNotConfigured("AIバックエンドが設定されていません(OPENCODE_URL / OPENROUTER_API_KEY)")

    instruction = (
        "あなたは製造品質保証の専門AIです。以下の不適合報告書を 4M(Man/Machine/Material/Method)"
        "の観点で分類し、根本原因の要因と具体的な改善提案を提示してください。\n\n"
        f"{report_text}"
    )

    if backend == "opencode":
        result = opencode_client.ask_json(
            system="あなたは製造品質保証の専門AIです。日本語で回答してください。",
            prompt=f"{instruction}\n\n{_schema_prompt(_analysis_schema())}",
        )
    else:
        client = _get_client()
        message = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": instruction}],
            output_config={"format": {"type": "json_schema", "schema": _analysis_schema()}},
        )
        result = _first_json(message)

    if result.get("category_4m") not in _4M_VALUES:
        raise RuntimeError(f"4M分類が不正です: {result.get('category_4m')!r}")
    if not isinstance(result.get("improvements"), list):
        result["improvements"] = [str(result.get("improvements", ""))]
    return result


# --- 写真のAI外観アシスト(docs/10 B-4) ---

_PHOTO_INSTRUCTION = (
    "あなたは製造業の品質検査員です。示された現場写真を観察し、見えるものだけを述べてください。"
    "写真から判断できないことは「写真からは判断できません」と書き、推測を事実のように述べないこと。"
)


def describe_defect_photo(file_bytes: bytes, media_type: str, filename: str) -> dict:
    """現場写真から欠陥の観察所見・現象候補を返す(vision)。"""
    backend = ai_backend()
    if backend == "none":
        raise LLMNotConfigured("AIバックエンドが設定されていません(OPENCODE_URL / OPENROUTER_API_KEY)")

    b64 = base64.standard_b64encode(file_bytes).decode("utf-8")
    prompt = (
        "この写真について JSON で返してください。\n"
        '形式: {"observation": "観察所見(2〜3文)", '
        '"phenomenon_candidates": ["現象分類の候補(例: 表面キズ, バリ残り, 寸法公差外れ)"], '
        '"notes": "撮影改善の提案など(任意)"}'
    )
    if backend == "opencode":
        return opencode_client.ask_json(
            system=_PHOTO_INSTRUCTION,
            prompt=prompt,
            files=[{"mime": media_type, "filename": filename, "b64": b64}],
        )
    client = _get_client()
    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
            {"type": "text", "text": _PHOTO_INSTRUCTION + "\n" + prompt},
        ]}],
    )
    return _first_json(message)
