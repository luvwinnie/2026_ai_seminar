#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""コーパスの語彙から「話し言葉 → 資料上の用語」対応表を作る。

LLM に候補を出させ、コーパスで裏を取る一般的な作り方:
  1. 全報告書の部品名・現象・原因/対策文から名詞的な語を集める(頻度順)
  2. 上位語を LLM に渡し「現場の人が代わりに使いそうな言い方」を出させる
  3. **出力をそのまま信じない。** 対応先の語がコーパスに実在するものだけ採用し、
     実在しない語(LLMの尤もらしい造語)は synonyms_rejected.json に捨てる
  4. 既存の手書き辞書(services/synonyms.json)に無いグループだけを
     services/synonyms_generated.json に書く(hybrid が両方を読む)

使い方(バックエンド環境変数が要る。Docker 内での実行を推奨):
  docker compose exec backend python scripts/build_synonyms.py            # 候補表示のみ
  docker compose exec backend python scripts/build_synonyms.py --apply    # 書き込み
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessionLocal  # noqa: E402
from models import DefectReport  # noqa: E402
from services import opencode_client  # noqa: E402
from services.hybrid import tokenize  # noqa: E402

BASE = Path(__file__).parent.parent / "services"
OUT = BASE / "synonyms_generated.json"
REJECTED = BASE / "synonyms_rejected.json"
APPLY = "--apply" in sys.argv
TOPN = 40

# 用語として意味を持たない語(数量・一般語)
STOP = set(
    """こと もの ため 場合 とき 以下 以上 未満 確認 実施 発生 対応 追加 変更 使用 加工
    測定 検査 作業 部品 報告 内容 原因 対策 状態 不良 不適合 mm 個 件 箇所""".split()
)


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "")


def main() -> None:
    db = SessionLocal()
    rows = db.query(DefectReport).all()
    corpus_text = norm(
        " ".join(
            " ".join(filter(None, [r.part_name, r.phenomenon, r.defect_description, r.cause, r.countermeasure]))
            for r in rows
        )
    )

    # 1) 語彙収集(2文字以上の日本語トークン、頻度順)
    counts = Counter(
        t for t in tokenize(corpus_text) if len(t) >= 2 and t not in STOP and re.search(r"[ぁ-ヶ一-龠]", t)
    )
    terms = [w for w, _ in counts.most_common(TOPN)]
    print(f"コーパス語彙(上位{len(terms)}): {terms[:15]} …")

    # 2) LLM に言い換え候補を出させる
    if not opencode_client.is_configured():
        print("OpenCode 未設定のため中止(候補生成に LLM が必要)")
        return
    res = opencode_client.ask_json(
        "あなたは製造現場の用語に詳しい編集者です。JSONだけを返してください。",
        "次の各用語について、製造現場の人が口頭・チャットで代わりに使いそうな言い方を"
        "0〜3個ずつ挙げてください(思いつかなければ空配列)。\n"
        f"用語: {json.dumps(terms, ensure_ascii=False)}\n"
        '出力形式: {"synonyms": {"用語": ["言い換え1", ...], ...}}',
    )
    raw = res.get("synonyms") or {}

    # 3) 検証: 元語がコーパスに実在すること(必須)。言い換えは新規語として採用可
    existing = json.loads((BASE / "synonyms.json").read_text(encoding="utf-8")).get("groups", [])
    known = {norm(w) for g in existing for w in g}
    groups, rejected = [], {}
    for term, alts in raw.items():
        t = norm(term)
        if t not in corpus_text:
            rejected[term] = {"reason": "元語がコーパスに実在しない", "alts": alts}
            continue
        alts = [norm(a) for a in alts if a and norm(a) != t]
        if not alts:
            continue
        if t in known or any(a in known for a in alts):
            rejected[term] = {"reason": "既存辞書と重複", "alts": alts}
            continue
        groups.append([t] + alts)

    print(f"採用 {len(groups)} グループ / 破棄 {len(rejected)} 件")
    for g in groups[:10]:
        print("  ", g)

    if APPLY:
        OUT.write_text(json.dumps({"groups": groups}, ensure_ascii=False, indent=1), encoding="utf-8")
        REJECTED.write_text(json.dumps(rejected, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"書き込み: {OUT.name} / {REJECTED.name}(検索側は自動で読み込む)")
    else:
        print("(--apply で services/synonyms_generated.json に書き込み)")


if __name__ == "__main__":
    main()
