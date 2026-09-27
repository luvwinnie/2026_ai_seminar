"""報告書の作成・更新・絞り込みの共通ロジック。

REST ルーター(routers/reports.py)と MCP ツール(services/mcp_server.py)の
両方から使う。二重実装を避けるためここに集約する。
"""
from __future__ import annotations

import re

from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Query, Session

from models import DefectReport


def _parse_date(v):
    """'YYYY-MM-DD' 文字列を date へ。date はそのまま、解釈不能は None。"""
    import datetime as _dt

    if isinstance(v, _dt.date):
        return v
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None

# ソート指定に使えるカラム
SORTABLE = {
    "occurrence_date": DefectReport.occurrence_date,
    "report_date": DefectReport.report_date,
    "defect_id": DefectReport.defect_id,
    "severity": DefectReport.severity,
    "created_at": DefectReport.created_at,
    "total_cost": DefectReport.total_cost,
}


class ReportServiceError(Exception):
    """業務エラー(REST 側では 409 等に変換する)。"""


def next_defect_id(db: Session) -> str:
    """`KZ25-` + 連番で採番する。"""
    max_n = 0
    for (defect_id,) in db.query(DefectReport.defect_id).all():
        m = re.match(r"KZ25-(\d+)", defect_id or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"KZ25-{max_n + 1:04d}"


def sum_costs(data: dict) -> float | None:
    parts = [
        data.get("material_cost"),
        data.get("processing_cost"),
        data.get("outsourcing_cost"),
        data.get("other_cost"),
    ]
    vals = [float(p) for p in parts if p is not None]
    return sum(vals) if vals else None


def build_report_query(
    db: Session,
    *,
    q: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    machine: str | None = None,
    process: str | None = None,
    customer: str | None = None,
    operator: str | None = None,
    phenomenon: str | None = None,
    category_4m: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str = "-occurrence_date",
) -> Query:
    """絞り込み+ソート済みのクエリを返す(count / offset / limit は呼び出し側)。"""
    query = db.query(DefectReport)

    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                DefectReport.defect_id.like(like),
                DefectReport.part_number.like(like),
                DefectReport.part_name.like(like),
                DefectReport.defect_description.like(like),
            )
        )
    if status:
        query = query.filter(DefectReport.status == status)
    if severity:
        query = query.filter(DefectReport.severity == severity)
    if machine:
        query = query.filter(DefectReport.machine_name == machine)
    if process:
        query = query.filter(DefectReport.process == process)
    if customer:
        query = query.filter(DefectReport.customer == customer)
    if operator:
        query = query.filter(DefectReport.operator_name == operator)
    if phenomenon:
        query = query.filter(DefectReport.phenomenon == phenomenon)
    if category_4m:
        query = query.filter(DefectReport.category_4m == category_4m)
    # 文字列日付は date 型へ変換(PostgreSQL は date と varchar を比較できない。
    # SQLite は通ってしまうためテストでは気付けない)。不正な形式は無視して全件側に倒す
    if date_from and (d := _parse_date(date_from)) is not None:
        query = query.filter(DefectReport.occurrence_date >= d)
    if date_to and (d := _parse_date(date_to)) is not None:
        query = query.filter(DefectReport.occurrence_date <= d)

    field = sort[1:] if sort.startswith("-") else sort
    column = SORTABLE.get(field, DefectReport.occurrence_date)
    order = desc if sort.startswith("-") else asc
    return query.order_by(order(column))


def create_report_core(db: Session, data: dict) -> DefectReport:
    """新規作成(採番・費用合算・マスタ自動登録・Chroma upsert)。"""
    from routers.masters import ensure_masters
    from services import rag

    if not data.get("defect_id"):
        data["defect_id"] = next_defect_id(db)
    elif db.query(DefectReport).filter_by(defect_id=data["defect_id"]).first():
        raise ReportServiceError("defect_id が既に存在します")

    if data.get("total_cost") is None:
        data["total_cost"] = sum_costs(data)

    report = DefectReport(**data)
    db.add(report)
    db.commit()
    db.refresh(report)

    ensure_masters(db, report)
    rag.upsert(report)
    return report


def update_report_core(db: Session, report: DefectReport, patch: dict) -> DefectReport:
    """部分更新(マスタ自動登録・Chroma 再 upsert)。"""
    from routers.masters import ensure_masters
    from services import rag

    for key, value in patch.items():
        setattr(report, key, value)

    db.commit()
    db.refresh(report)

    ensure_masters(db, report)
    rag.upsert(report)
    return report


def report_to_dict(report: DefectReport) -> dict:
    """MCP ツール用: 型を保ったまま dict 化(+defect_rate)。"""
    out = {}
    for c in DefectReport.__table__.columns:
        v = getattr(report, c.name)
        out[c.name] = v.isoformat() if hasattr(v, "isoformat") else v
    if report.production_count:
        out["defect_rate"] = round((report.defect_count or 0) / report.production_count, 4)
    else:
        out["defect_rate"] = None
    return out
