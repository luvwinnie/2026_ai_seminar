"""ダッシュボード集計・p管理図・ルールベース予兆アラート。

すべて SQL/Python のみで完結し、LLM は使わない(docs/04 §4-5)。
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models import DefectReport


def _to_date(value) -> date | None:
    """文字列 / date を date に正規化する。"""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _load(db: Session, date_from=None, date_to=None) -> list[DefectReport]:
    """発生日レンジで報告書を読み込む。"""
    q = db.query(DefectReport)
    df = _to_date(date_from)
    dt = _to_date(date_to)
    if df:
        q = q.filter(DefectReport.occurrence_date >= df)
    if dt:
        q = q.filter(DefectReport.occurrence_date <= dt)
    return q.all()


def _num(v) -> float:
    return float(v) if v is not None else 0.0


def _rate(defects: int, production: int) -> float:
    return defects / production if production else 0.0


def _group_metrics(rows: list[DefectReport], key) -> list[dict]:
    """キー別に reports/defects/defect_rate/total_cost を集計(件数降順)。"""
    agg: dict[str, dict] = defaultdict(
        lambda: {"reports": 0, "defects": 0, "production": 0, "total_cost": 0.0}
    )
    for r in rows:
        name = key(r) or "未設定"
        a = agg[name]
        a["reports"] += 1
        a["defects"] += r.defect_count or 0
        a["production"] += r.production_count or 0
        a["total_cost"] += _num(r.total_cost)
    out = []
    for name, a in agg.items():
        out.append(
            {
                "name": name,
                "reports": a["reports"],
                "defects": a["defects"],
                "defect_rate": _rate(a["defects"], a["production"]),
                "total_cost": round(a["total_cost"], 2),
            }
        )
    out.sort(key=lambda x: x["reports"], reverse=True)
    return out


def statistics(db: Session, date_from=None, date_to=None) -> dict:
    """ダッシュボード統計(docs/04 §4)。"""
    rows = _load(db, date_from, date_to)

    total_reports = len(rows)
    total_defects = sum(r.defect_count or 0 for r in rows)
    total_production = sum(r.production_count or 0 for r in rows)
    total_cost = sum(_num(r.total_cost) for r in rows)
    recurrence = sum(1 for r in rows if r.is_recurrence)
    open_count = sum(1 for r in rows if r.status == "open")

    defect_rate = _rate(total_defects, total_production)
    fpy = (total_production - total_defects) / total_production if total_production else 0.0

    kpi = {
        "total_reports": total_reports,
        "total_defects": total_defects,
        "total_production": total_production,
        "defect_rate": defect_rate,
        "fpy": fpy,
        "total_cost": round(total_cost, 2),
        "recurrence_rate": (recurrence / total_reports) if total_reports else 0.0,
        "open_count": open_count,
    }

    # --- 月次推移 ---
    monthly: dict[str, dict] = defaultdict(
        lambda: {"reports": 0, "defects": 0, "production": 0}
    )
    for r in rows:
        if not r.occurrence_date:
            continue
        m = r.occurrence_date.strftime("%Y-%m")
        monthly[m]["reports"] += 1
        monthly[m]["defects"] += r.defect_count or 0
        monthly[m]["production"] += r.production_count or 0
    monthly_trend = [
        {
            "month": m,
            "reports": v["reports"],
            "defects": v["defects"],
            "production": v["production"],
            "defect_rate": _rate(v["defects"], v["production"]),
        }
        for m, v in sorted(monthly.items())
    ]

    # --- 現象パレート ---
    phen: dict[str, int] = defaultdict(int)
    for r in rows:
        phen[r.phenomenon or "未分類"] += 1
    phen_sorted = sorted(phen.items(), key=lambda x: x[1], reverse=True)
    pareto = []
    cum = 0
    for name, count in phen_sorted:
        cum += count
        pareto.append(
            {
                "name": name,
                "count": count,
                "ratio": (count / total_reports) if total_reports else 0.0,
                "cumulative_ratio": (cum / total_reports) if total_reports else 0.0,
            }
        )

    # --- 4M分類 ---
    by_4m_map: dict[str, int] = defaultdict(int)
    for r in rows:
        by_4m_map[r.category_4m or "未分類"] += 1
    by_4m = [{"name": k, "count": v} for k, v in sorted(by_4m_map.items(), key=lambda x: x[1], reverse=True)]

    # --- severity ---
    sev_map: dict[str, int] = defaultdict(int)
    for r in rows:
        sev_map[r.severity or "未設定"] += 1
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    by_severity = [
        {"name": k, "count": v}
        for k, v in sorted(sev_map.items(), key=lambda x: sev_order.get(x[0], 99))
    ]

    return {
        "kpi": kpi,
        "monthly_trend": monthly_trend,
        "pareto_phenomenon": pareto,
        "by_machine": _group_metrics(rows, lambda r: r.machine_name),
        "by_operator": _group_metrics(rows, lambda r: r.operator_name),
        "by_process": _group_metrics(rows, lambda r: r.process),
        "by_customer": _group_metrics(rows, lambda r: r.customer),
        "by_4m": by_4m,
        "by_severity": by_severity,
    }


def control_chart(db: Session, months: int = 12) -> dict:
    """p管理図(不適合率の管理図)。

    UCL/LCL = p̄ ± 3√(p̄(1−p̄)/n)、LCL は 0 で下限クリップ。
    """
    rows = db.query(DefectReport).all()
    monthly: dict[str, dict] = defaultdict(lambda: {"n": 0, "defects": 0})
    for r in rows:
        if not r.occurrence_date:
            continue
        m = r.occurrence_date.strftime("%Y-%m")
        monthly[m]["n"] += r.production_count or 0
        monthly[m]["defects"] += r.defect_count or 0

    periods = sorted(monthly.keys())[-months:]

    total_defects = sum(monthly[m]["defects"] for m in periods)
    total_n = sum(monthly[m]["n"] for m in periods)
    p_bar = total_defects / total_n if total_n else 0.0

    items = []
    for m in periods:
        n = monthly[m]["n"]
        defects = monthly[m]["defects"]
        p = defects / n if n else 0.0
        if n > 0:
            sigma = math.sqrt(p_bar * (1 - p_bar) / n)
        else:
            sigma = 0.0
        ucl = p_bar + 3 * sigma
        lcl = max(0.0, p_bar - 3 * sigma)
        items.append(
            {
                "period": m,
                "n": n,
                "defects": defects,
                "p": p,
                "ucl": ucl,
                "lcl": lcl,
            }
        )

    return {"items": items, "p_bar": p_bar}


def alerts(db: Session) -> dict:
    """ルールベースの予兆アラート(docs/04 §5)。

    「直近」はデータ内の最新発生日を基準にする(固定の模擬データでもデモが成立するように)。
    """
    rows = db.query(DefectReport).all()
    items: list[dict] = []
    if not rows:
        return {"items": items}

    dates = [r.occurrence_date for r in rows if r.occurrence_date]
    ref = max(dates) if dates else date.today()

    last30 = ref - timedelta(days=30)
    last60 = ref - timedelta(days=60)

    # 全期間の機械別不良率
    machine_all: dict[str, dict] = defaultdict(lambda: {"defects": 0, "production": 0})
    for r in rows:
        m = r.machine_name or "未設定"
        machine_all[m]["defects"] += r.defect_count or 0
        machine_all[m]["production"] += r.production_count or 0
    overall_rate = _rate(
        sum(v["defects"] for v in machine_all.values()),
        sum(v["production"] for v in machine_all.values()),
    )

    # ルール1: 直近30日で不良率が全期間平均の1.5倍超の機械
    machine_recent: dict[str, dict] = defaultdict(lambda: {"defects": 0, "production": 0})
    for r in rows:
        if r.occurrence_date and r.occurrence_date >= last30:
            m = r.machine_name or "未設定"
            machine_recent[m]["defects"] += r.defect_count or 0
            machine_recent[m]["production"] += r.production_count or 0
    for m, v in machine_recent.items():
        if v["production"] == 0:
            continue
        rate = _rate(v["defects"], v["production"])
        if overall_rate > 0 and rate > overall_rate * 1.5:
            items.append(
                {
                    "level": "warning",
                    "title": f"機械 {m} の不良率が上昇",
                    "message": (
                        f"直近30日の不良率 {rate:.2%} が全期間平均 {overall_rate:.2%} の"
                        f"1.5倍を超えています。"
                    ),
                    "related": {"machine": m},
                }
            )

    # ルール2: 同一現象×同一機械が直近60日に3件以上
    combo: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        if r.occurrence_date and r.occurrence_date >= last60:
            combo[(r.machine_name or "未設定", r.phenomenon or "未分類")] += 1
    for (machine, phenomenon), count in combo.items():
        if count >= 3:
            items.append(
                {
                    "level": "critical",
                    "title": f"{machine} で {phenomenon} が多発",
                    "message": f"直近60日で同一機械・同一現象が {count} 件発生しています。",
                    "related": {"machine": machine, "phenomenon": phenomenon},
                }
            )

    # ルール3: 再発フラグ付きが直近30日に発生
    recur = [
        r for r in rows if r.is_recurrence and r.occurrence_date and r.occurrence_date >= last30
    ]
    for r in recur:
        items.append(
            {
                "level": "info",
                "title": f"再発案件が発生({r.defect_id})",
                "message": (
                    f"{r.machine_name} / {r.phenomenon} の再発が報告されています"
                    f"({r.occurrence_date})。"
                ),
                "related": {"machine": r.machine_name, "phenomenon": r.phenomenon},
            }
        )

    return {"items": items}
