"""週次品質ダイジェスト生成(docs/10 A-2)。

決定論パート(KPI比較・重大案件・アラート)を必ず含み、OpenCode が使えるときだけ
AIの「所見と推奨アクション」を追記する二層構成(AI不通でもレポートは成立する)。
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from models import ChatFeedback, DefectReport, WeeklyDigest
from services import opencode_client, stats


def _ref_date(db: Session) -> date:
    """基準日 = データ内の最新発生日(固定の模擬データでもデモが成立するように)。"""
    latest = (
        db.query(DefectReport.occurrence_date)
        .order_by(DefectReport.occurrence_date.desc())
        .first()
    )
    return latest[0] if latest and latest[0] else date.today()


def _fmt_pct(v: float | None) -> str:
    return f"{v * 100:.1f}%" if isinstance(v, (int, float)) else "-"


def generate(db: Session, days: int = 7) -> WeeklyDigest:
    """直近 days 日のダイジェストを生成して保存する。"""
    end = _ref_date(db)
    start = end - timedelta(days=days - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)

    cur = stats.statistics(db, start.isoformat(), end.isoformat())
    prev = stats.statistics(db, prev_start.isoformat(), prev_end.isoformat())
    alerts = stats.alerts(db)["items"]

    rows = (
        db.query(DefectReport)
        .filter(DefectReport.occurrence_date >= start, DefectReport.occurrence_date <= end)
        .order_by(DefectReport.occurrence_date.desc())
        .all()
    )
    criticals = [r for r in rows if r.severity == "critical"]
    opens = [r for r in rows if r.status == "open"]

    k, pk = cur.get("kpi", {}), prev.get("kpi", {})

    # チャット回答へのフィードバック(今期間ぶん)
    fb = (
        db.query(ChatFeedback)
        .filter(ChatFeedback.created_at >= start, ChatFeedback.created_at <= end + timedelta(days=1))
        .all()
    )
    fb_up = sum(1 for f in fb if f.rating > 0)
    fb_down = sum(1 for f in fb if f.rating < 0)

    def delta(key: str, pct: bool = False) -> str:
        a, b = k.get(key), pk.get(key)
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return "-"
        d = a - b
        arrow = "▲" if d > 0 else ("▼" if d < 0 else "→")
        if pct:
            return f"{arrow}{abs(d) * 100:.1f}pt"
        # 金額など大きい値も指数表記にせず桁区切りで(例: ▲1,189,570円)
        v = abs(d)
        return f"{arrow}{v:,.0f}" if v >= 1000 or v == int(v) else f"{arrow}{v:g}"

    lines = [
        f"# 週次品質ダイジェスト({start} 〜 {end})",
        "",
        "## 今週のKPI(前週比)",
        "",
        "| 指標 | 今週 | 前週比 |",
        "|---|---|---|",
        f"| 報告書数 | {k.get('total_reports', 0)}件 | {delta('total_reports')} |",
        f"| 不適合数 | {k.get('total_defects', 0)}個 | {delta('total_defects')} |",
        f"| 不良率 | {_fmt_pct(k.get('defect_rate'))} | {delta('defect_rate', pct=True)} |",
        f"| 損失額 | {k.get('total_cost', 0):,.0f}円 | {delta('total_cost')} |",
        "",
        f"## 重大(critical)案件: {len(criticals)}件",
    ]
    if fb:
        # KPI表の末尾(空行の前)に差し込む
        lines.insert(-2, f"| AI回答への評価 | 👍{fb_up} / 👎{fb_down} | - |")
    for r in criticals[:5]:
        lines.append(f"- [{r.defect_id}] {r.machine_name} / {r.phenomenon} — {(r.defect_description or '')[:60]}")
    lines += ["", f"## 未対応(open): {len(opens)}件"]
    for r in opens[:5]:
        lines.append(f"- [{r.defect_id}] {r.occurrence_date} {r.machine_name} / {r.phenomenon}")
    lines += ["", f"## アラート: {len(alerts)}件"]
    for a in alerts[:6]:
        lines.append(f"- **{a['title']}** — {a['message']}")

    md = "\n".join(lines)
    backend = "none"

    # AI所見(OpenCode があるときだけ)
    if opencode_client.is_configured():
        try:
            comment = opencode_client.ask(
                "あなたは製造業の品質保証マネージャです。事実の捏造をせず、与えられた数値と"
                "アラートだけに基づいて簡潔に書いてください。",
                "以下の週次品質データから「所見(3行以内)」と「今週の推奨アクション(箇条書き3つ)」を"
                f"Markdownで書いてください。見出しは `## AI所見` と `## 推奨アクション`。\n\n{md}",
            )
            if comment.strip():
                md += "\n\n" + comment.strip()
                backend = "opencode"
        except Exception:
            pass  # AI不通でも決定論パートだけで成立させる

    digest = WeeklyDigest(period_start=start, period_end=end, content_md=md, ai_backend=backend)
    db.add(digest)
    db.commit()
    db.refresh(digest)
    return digest


def to_dict(d: WeeklyDigest) -> dict:
    return {
        "id": d.id,
        "period_start": d.period_start.isoformat(),
        "period_end": d.period_end.isoformat(),
        "content_md": d.content_md,
        "ai_backend": d.ai_backend,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }
