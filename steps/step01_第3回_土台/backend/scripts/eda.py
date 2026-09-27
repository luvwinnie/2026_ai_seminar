"""第3回 演習: 簡単な EDA(探索的データ分析)。

pandas で共有CSV(../../data/defect_reports.csv)を読み込み、
- 現象別の件数
- 機械別の不良率(不適合数合計 / 加工数合計)
- 月別の件数
を print する。

実行: python scripts/eda.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

# backend/scripts/ から見て共有 data は 4階層上(scripts→backend→step→steps→example_app)/data
BASE = Path(__file__).resolve().parents[4] / "data" / "defect_reports.csv"


def main() -> None:
    if not BASE.exists():
        raise SystemExit(f"CSVが見つかりません: {BASE}")

    df = pd.read_csv(BASE)
    print(f"読み込み: {len(df)} 件  期間: {df['occurrence_date'].min()} 〜 {df['occurrence_date'].max()}\n")

    # 1) 現象別の件数(降順)
    print("=== 現象別 件数 ===")
    print(df["phenomenon"].value_counts().to_string())
    print()

    # 2) 機械別の不良率 = 不適合数合計 / 加工数合計
    print("=== 機械別 不良率 ===")
    by_machine = df.groupby("machine_name").agg(
        defects=("defect_count", "sum"), production=("production_count", "sum")
    )
    by_machine["defect_rate"] = by_machine["defects"] / by_machine["production"]
    print(by_machine.sort_values("defect_rate", ascending=False).round(4).to_string())
    print()

    # 3) 月別の件数
    print("=== 月別 件数 ===")
    month = pd.to_datetime(df["occurrence_date"]).dt.to_period("M").astype(str)
    print(month.value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
