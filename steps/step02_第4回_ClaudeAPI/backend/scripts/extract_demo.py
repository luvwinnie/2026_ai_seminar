"""第4回 演習: 構造化出力(JSON 抽出)の単体デモ。

不具合報告の自由文1件を、JSON Schema を使って Claude に構造化抽出させて print する。
docs/04 §7 の規則に従う: temperature/top_p/top_k/budget_tokens は送らない。
構造化出力は output_config={"format": {"type": "json_schema", "schema": ...}}。

実行:
  export ANTHROPIC_API_KEY=sk-...
  python scripts/extract_demo.py
API キー未設定時は、送信予定のスキーマを表示して終了する。
"""
from __future__ import annotations

import json
import os

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

# 自由記述の不具合報告(演習用サンプル)
SAMPLE_TEXT = (
    "2025年10月3日、旋盤(QUICK TURN 250MSY)でシャフトを50個加工したところ、3個で外径が公差を"
    "0.02mm超過する寸法不良が発生した。作業者は山田。原因は工具摩耗の見落としと考えられる。"
    "対策として工具交換周期の見直しを行う。材料費は約12000円、社内加工費は約35000円。"
)

# 抽出したいフィールドのスキーマ(defect_reports のサブセット)。不明値は null 許容。
SCHEMA = {
    "type": "object",
    "properties": {
        "occurrence_date": {"type": ["string", "null"]},
        "process": {"type": ["string", "null"]},
        "machine_name": {"type": ["string", "null"]},
        "operator_name": {"type": ["string", "null"]},
        "part_name": {"type": ["string", "null"]},
        "production_count": {"type": ["integer", "null"]},
        "defect_count": {"type": ["integer", "null"]},
        "phenomenon": {"type": ["string", "null"]},
        "defect_description": {"type": ["string", "null"]},
        "cause": {"type": ["string", "null"]},
        "countermeasure": {"type": ["string", "null"]},
        "material_cost": {"type": ["number", "null"]},
        "processing_cost": {"type": ["number", "null"]},
        "severity": {"type": ["string", "null"]},
    },
    "required": [
        "occurrence_date",
        "process",
        "machine_name",
        "operator_name",
        "part_name",
        "production_count",
        "defect_count",
        "phenomenon",
        "defect_description",
        "cause",
        "countermeasure",
        "material_cost",
        "processing_cost",
        "severity",
    ],
    "additionalProperties": False,
}

INSTRUCTION = (
    "次の不具合報告の自由文から、指定のJSONスキーマに沿って項目を抽出してください。"
    "日付は YYYY-MM-DD、severity は critical/high/medium/low に正規化。"
    "読み取れない項目は null。\n\n" + SAMPLE_TEXT
)


def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY が未設定です。送信予定の JSON Schema を表示します:\n")
        print(json.dumps(SCHEMA, ensure_ascii=False, indent=2))
        return

    import anthropic

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": INSTRUCTION}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    # 最初の text ブロックが JSON
    for block in message.content:
        if block.type == "text":
            data = json.loads(block.text)
            print(json.dumps(data, ensure_ascii=False, indent=2))
            break


if __name__ == "__main__":
    main()
