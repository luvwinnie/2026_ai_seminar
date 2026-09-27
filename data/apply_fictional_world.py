# -*- coding: utf-8 -*-
"""fictional_world.json(架空工場の世界観)を教材一式へ適用する。

置換対象:
  - data/generate_mock_data.py     (機械・客先の語彙プール)
  - app/backend/routers/masters.py (マスタseed)
  - app/backend/tests/test_api.py  (客先名の期待値)
  - docs/03_データモデル設計書.md / docs/05_UI設計書.md (例示)
  - steps/*/frontend/src/constants/vocab.ts (教材スナップショット)
適用後に generate_mock_data.py を実行して CSV/帳票を再生成すること。
"""
import json
import pathlib

DATA = pathlib.Path(__file__).parent
ROOT = DATA.parent
world = json.loads((DATA / "fictional_world.json").read_text(encoding="utf-8"))

machine_map: dict = {k: v for k, v in world["machine_mapping"].items() if k != v}
customer_map: dict = world["customers"]

targets = [
    DATA / "generate_mock_data.py",
    ROOT / "app/backend/routers/masters.py",
    ROOT / "app/backend/tests/test_api.py",
    ROOT / "docs/03_データモデル設計書.md",
    ROOT / "docs/05_UI設計書.md",
]
targets += sorted(ROOT.glob("steps/*/frontend/src/constants/vocab.ts"))

# 長い旧名から先に置換(部分一致の巻き込み防止: GENOS M660-V を GENOS M560-V より先に等)
repl = sorted(machine_map.items(), key=lambda kv: -len(kv[0]))
repl += sorted(customer_map.items(), key=lambda kv: -len(kv[0]))

for path in targets:
    if not path.exists():
        print(f"skip (not found): {path}")
        continue
    text = orig = path.read_text(encoding="utf-8")
    for old, new in repl:
        text = text.replace(old, new)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        print(f"patched: {path.relative_to(ROOT)}")
    else:
        print(f"no change: {path.relative_to(ROOT)}")

print("done. 次: python3 generate_mock_data.py で CSV/帳票を再生成")
