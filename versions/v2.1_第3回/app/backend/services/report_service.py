"""報告書を読む処理（04_API設計書.md §4・§5・§8.2）。REST の API と MCP の道具が同じ処理を使う。"""

from collections import defaultdict
from datetime import date

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from models import DefectReport, MasterItem
from schemas import ReportOut
from seed import MASTER_COLUMNS

# 重大度は重さの順で並べる（文字列の順では並べない）
SEVERITY_RANK = case(
    {"low": 1, "medium": 2, "high": 3, "critical": 4},
    value=DefectReport.severity,
    else_=0,
)

SORT_COLUMNS = {
    "occurrence_date": DefectReport.occurrence_date,
    "report_date": DefectReport.report_date,
    "defect_id": DefectReport.defect_id,
    "severity": SEVERITY_RANK,
    "created_at": DefectReport.created_at,
    "total_cost": DefectReport.total_cost,
    "defect_count": DefectReport.defect_count,
}

# 完全一致で絞る条件：引数の名前 → 列
EXACT_FILTERS = {
    "status": DefectReport.status,
    "severity": DefectReport.severity,
    "machine": DefectReport.machine_name,
    "process": DefectReport.process,
    "customer": DefectReport.customer,
    "operator": DefectReport.operator_name,
    "phenomenon": DefectReport.phenomenon,
    "category_4m": DefectReport.category_4m,
}

# キーワード検索（search_reports）で見る列。snippet もこの順で探す
SEARCH_COLUMNS = ["defect_description", "cause", "countermeasure", "part_name", "phenomenon"]

# 一覧の道具が返す要約の項目
SUMMARY_FIELDS = [
    "defect_id", "occurrence_date", "customer", "process", "machine_name", "operator_name",
    "part_name", "phenomenon", "severity", "status", "production_count", "defect_count",
    "defect_rate", "total_cost",
]


def order_by_for(sort: str):
    """sort の値から並べ替えを作る。同じ値どうしは defect_id で、同じ向きに並べる。"""
    descending = sort.startswith("-")
    column = SORT_COLUMNS.get(sort.lstrip("-"), DefectReport.occurrence_date)
    if descending:
        return [column.desc(), DefectReport.defect_id.desc()]
    return [column.asc(), DefectReport.defect_id.asc()]


def filter_conditions(q: str | None = None, date_from: date | None = None, date_to: date | None = None,
                      **exact: str | None) -> list:
    """絞り込みの条件を作る。条件はすべて AND で組む。"""
    conditions = []
    if q and q.strip():
        keyword = q.strip()
        conditions.append(or_(
            DefectReport.defect_id.icontains(keyword, autoescape=True),
            DefectReport.part_number.icontains(keyword, autoescape=True),
            DefectReport.part_name.icontains(keyword, autoescape=True),
            DefectReport.defect_description.icontains(keyword, autoescape=True),
        ))
    for name, value in exact.items():
        if value:
            conditions.append(EXACT_FILTERS[name] == value)
    if date_from:
        conditions.append(DefectReport.occurrence_date >= date_from)
    if date_to:
        conditions.append(DefectReport.occurrence_date <= date_to)
    return conditions


def list_reports(db: Session, *, limit: int = 50, offset: int = 0, sort: str = "-occurrence_date",
                 q: str | None = None, date_from: date | None = None, date_to: date | None = None,
                 **exact: str | None) -> tuple[int, list[DefectReport]]:
    """条件に合う件数と、そのページの報告書を返す。"""
    conditions = filter_conditions(q, date_from, date_to, **exact)
    total = db.scalar(select(func.count()).select_from(DefectReport).where(*conditions))
    items = db.scalars(
        select(DefectReport).where(*conditions).order_by(*order_by_for(sort)).limit(limit).offset(offset)
    ).all()
    return total, list(items)


def get_report(db: Session, defect_id: str) -> DefectReport | None:
    return db.scalar(select(DefectReport).where(DefectReport.defect_id == defect_id))


def report_to_dict(report: DefectReport) -> dict:
    """報告書1件を JSON にできる形にする（全列＋defect_rate。defect_rate は小数4桁）。"""
    data = ReportOut.model_validate(report).model_dump(mode="json")
    if data["defect_rate"] is not None:
        data["defect_rate"] = round(data["defect_rate"], 4)
    return data


def report_summary(report: DefectReport) -> dict:
    data = report_to_dict(report)
    return {key: data[key] for key in SUMMARY_FIELDS}


def search_reports(db: Session, query: str, top_k: int = 5, machine: str | None = None,
                   process: str | None = None) -> list[dict]:
    """キーワード検索（06_AI設計書.md §1.5）。空白で分けた語のどれかを部分一致で探し、語の出てくる回数で並べる。"""
    words = [word for word in query.split() if word]
    if not words:
        return []
    conditions = filter_conditions(machine=machine, process=process)
    conditions.append(or_(*[
        getattr(DefectReport, column).icontains(word, autoescape=True)
        for word in words for column in SEARCH_COLUMNS
    ]))
    results = []
    for report in db.scalars(select(DefectReport).where(*conditions)):
        texts = [getattr(report, column) or "" for column in SEARCH_COLUMNS]
        score = sum(text.lower().count(word.lower()) for text in texts for word in words)
        snippet = next(
            (text[:80] for text in texts if any(word.lower() in text.lower() for word in words)), ""
        )
        results.append({
            "defect_id": report.defect_id,
            "part_name": report.part_name,
            "machine_name": report.machine_name,
            "process": report.process,
            "phenomenon": report.phenomenon,
            "snippet": snippet,
            "score": score,
        })
    # score の高い順、同じなら報告書番号の新しい順
    results.sort(key=lambda r: r["defect_id"], reverse=True)
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]


def _ratio(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _group(reports: list[DefectReport], key) -> list[dict]:
    """名前ごとの件数・不適合数・損失。件数の多い順、同じなら名前の順。"""
    groups: dict = defaultdict(lambda: {"count": 0, "defect_units": 0, "total_loss": 0.0})
    for report in reports:
        group = groups[key(report)]
        group["count"] += 1
        group["defect_units"] += report.defect_count
        group["total_loss"] += report.total_cost or 0
    rows = [{"name": name, **values} for name, values in groups.items()]
    return sorted(rows, key=lambda r: (-r["count"], r["name"] or ""))


def statistics(db: Session, date_from: date | None = None, date_to: date | None = None) -> dict:
    """全体・期間の集計（04_API設計書.md §8.2）。期間は発生日で、両端を含む。"""
    reports = list(db.scalars(select(DefectReport).where(*filter_conditions(date_from=date_from, date_to=date_to))))
    total = len(reports)
    defect_units = sum(r.defect_count for r in reports)
    production_units = sum(r.production_count for r in reports)

    monthly: dict = defaultdict(lambda: {"reports": 0, "defect_units": 0})
    for report in reports:
        month = monthly[report.occurrence_date.strftime("%Y-%m")]
        month["reports"] += 1
        month["defect_units"] += report.defect_count

    pareto = []
    cumulative = 0
    for row in _group(reports, lambda r: r.phenomenon):
        cumulative += row["count"]
        pareto.append({
            "name": row["name"],
            "count": row["count"],
            "ratio": _ratio(row["count"], total),
            "cumulative_ratio": _ratio(cumulative, total),
        })

    return {
        "period": {
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
        "kpi": {
            "total_reports": total,
            "defect_units": defect_units,
            "production_units": production_units,
            "defect_rate": _ratio(defect_units, production_units),
            "total_loss": sum(r.total_cost or 0 for r in reports),
        },
        "monthly": [{"month": month, **values} for month, values in sorted(monthly.items())],
        "phenomenon_pareto": pareto,
        "by_machine": _group(reports, lambda r: r.machine_name),
        "by_operator": _group(reports, lambda r: r.operator_name),
        "by_process": _group(reports, lambda r: r.process),
        "by_customer": _group(reports, lambda r: r.customer),
        "by_category_4m": _group(reports, lambda r: r.category_4m),
        "by_severity": _group(reports, lambda r: r.severity),
    }


def masters_with_usage(db: Session) -> dict[str, list[dict]]:
    """6種のマスタと使用件数。使用件数は保存せず、報告書の列で数える。"""
    result = {}
    for category, column_name in MASTER_COLUMNS.items():
        column = getattr(DefectReport, column_name)
        usage = dict(db.execute(select(column, func.count()).group_by(column)).all())
        items = db.scalars(
            select(MasterItem)
            .where(MasterItem.category == category)
            .order_by(MasterItem.sort_order, MasterItem.name)
        )
        result[category] = [
            {
                "id": item.id,
                "category": item.category,
                "name": item.name,
                "sort_order": item.sort_order,
                "is_active": item.is_active,
                "usage_count": usage.get(item.name, 0),
            }
            for item in items
        ]
    return result
