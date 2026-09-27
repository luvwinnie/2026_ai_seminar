"""MCP(Model Context Protocol)サーバー — 不適合報告書データをツールとして公開。

OpenCode(や他の MCP クライアント)がチャット中に自律的に呼び出すツール群。
FastMCP の Streamable HTTP アプリとして main.py で /mcp にマウントされる。

設計方針:
- 読み取り7本+書き込み2本。docstring に「いつ使うか」を明示する
  (トリガー条件を書くとエージェントのツール選択精度が上がる)。
- 作成・更新は REST と同じ共通ロジック(services/report_service.py)を使う。
"""
from __future__ import annotations

from fastmcp import FastMCP

from database import SessionLocal
from models import DefectReport
from services import rag, stats
from services.report_service import (
    ReportServiceError,
    build_report_query,
    create_report_core,
    report_to_dict,
    update_report_core,
)

mcp = FastMCP(
    "defect-reports",
    instructions=(
        "製造業の不適合報告書(約120件、2025-04〜2026-03)を検索・参照・登録・更新するツール群。\n"
        "推奨ワークフロー: ①固有名詞(機械/客先等)の表記が不確かなら list_masters で確認 → "
        "②条件が明確なら list_defect_reports、内容が曖昧なら search_defect_reports → "
        "③深掘りは get_defect_report、集計は get_statistics。\n"
        "フィルタは完全一致。0件なら該当なしと伝え、指定条件を無断で外さない。\n"
        "Ontology: get_ontology_definitionで意味を確認し、resolve_ontology_entityでID解決、"
        "query_quality_ontologyで条件別の指標と関連CAPAを集計、traverse_ontology_relationで実関係をたどる。"
        "CAPAの変更前はpreview_capa_update。プレビューは保存・承認ではない。\n"
        "回答で報告書を参照した場合は [KZ25-XXXX] 形式で必ず引用すること。"
        "登録・更新(create/update)はユーザーが明示的に依頼した場合のみ行うこと。\n"
        "画面操作ツール(ui_navigate / ui_open_report / ui_new_report / ui_edit_report / "
        "ui_run_4m_analysis / ui_set_theme)は、「見せて/出して/開いて/〜にして/〜で表示」など"
        "表示を変える意図が読み取れる依頼で積極的に使い、操作した旨を回答に一言添えること。"
        "純粋な質問(「何件?」「原因は?」)にはチャットで答える。\n"
        "**毎ターン独立の原則: 報告書の項目値・内容を述べるときは、そのターンでデータツールを呼んで"
        "取得した結果だけを使う。前のターンの結果や会話履歴から内容を再構成しない(捏造になる)。**\n"
        "**画面を操作した・開いた・切り替えたと述べる前に、必ず該当の ui_* ツールを実際に呼ぶこと。**"
        "「KZ25-XXXXを開いて」は ui_open_report、「一覧を〜で出して/並び替えて」は ui_navigate。"
        "ツールを呼ばずに「表示しました/並び替えました」と主張してはならない"
        "(会話履歴に同様の操作があっても、毎回あらためて呼ぶ。ui_navigate は何度呼んでも安全)。"
        "画面操作はデータを変更しない(下書き・編集モードの入力/保存は利用者が行う)。"
        "一覧の全フィルタ・ソート・スマート検索、各画面の期間指定も ui_navigate で画面に反映できる。\n"
        "是正処置の推奨フロー: 類似事例は get_similar_reports → 対策案は draft_capa_actions(保存しない) → "
        "登録・状態変更(create/update_capa_action)は明示依頼のみ → 文書化は generate_8d_report。"
    ),
)

# 一覧系ツールが返す要約フィールド
_SUMMARY_FIELDS = (
    "defect_id",
    "occurrence_date",
    "customer",
    "process",
    "machine_name",
    "operator_name",
    "part_name",
    "phenomenon",
    "severity",
    "status",
    "production_count",
    "defect_count",
    "category_4m",
    "is_recurrence",
)


def _summary(r: DefectReport) -> dict:
    d = report_to_dict(r)
    out = {k: d.get(k) for k in _SUMMARY_FIELDS}
    out["defect_rate"] = d.get("defect_rate")
    return out


@mcp.tool
def list_defect_reports(
    machine: str | None = None,
    process: str | None = None,
    customer: str | None = None,
    operator: str | None = None,
    phenomenon: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    category_4m: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
    sort: str = "-occurrence_date",
) -> dict:
    """条件で絞り込んで不適合報告書の一覧を取得する。

    **機械名・工程・客先・期間・重要度・ステータスなど、条件がはっきりしている
    質問ではまずこれを使う。** 例:
    - 「GENOS M560-Vで最近多い不具合は?」→ machine="GENOS M560-V", sort="-occurrence_date"
    - 「今年のcritical案件」→ severity="critical", date_from="2026-01-01"
    - 「未対応の再発しやすい機械」→ status="open" で取得して集計

    フィルタは**完全一致**。正確な表記が不明なら先に list_masters で確認する。
    0件のときは条件を1つ減らして再試行すること。
    曖昧な内容検索(「〜のような不良」)には向かない → search_defect_reports を使う。

    Args:
        machine: 使用機械の完全一致(例: "GENOS M560-V", "QUICK TURN 250MSY", "TSL-550")
        process: 発生工程(旋盤 / フライス / マシニング / 研磨 / 溶接 / 組立 / 検査 / バリ取り)
        customer: 客先(例: "翠峰重工業")
        operator: 作業者名(姓)
        phenomenon: 現象分類(例: "寸法公差外れ", "穴位置ずれ", "表面キズ", "バリ残り", "工具破損")
        severity: critical / high / medium / low
        status: open / in_progress / completed
        category_4m: Man / Machine / Material / Method
        date_from, date_to: 発生日の範囲(YYYY-MM-DD)
        q: 自由語の部分一致(ID・部品番号・部品名・不具合内容)
        limit, offset: ページング(limit 最大100)
        sort: 並び順。"-occurrence_date"(新しい順・既定)/ "-total_cost"(損失大きい順)等
    Returns:
        {"total": 条件に合う全件数, "items": [報告書の要約(defect_rate含む)]}
    """
    db = SessionLocal()
    try:
        query = build_report_query(
            db,
            q=q,
            status=status,
            severity=severity,
            machine=machine,
            process=process,
            customer=customer,
            operator=operator,
            phenomenon=phenomenon,
            category_4m=category_4m,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
        )
        total = query.count()
        items = query.offset(max(offset, 0)).limit(min(max(limit, 1), 100)).all()
        return {"total": total, "items": [_summary(r) for r in items]}
    finally:
        db.close()


@mcp.tool
def search_defect_reports(
    query: str,
    top_k: int = 5,
    machine: str | None = None,
    process: str | None = None,
) -> list[dict]:
    """不適合報告書を意味検索する(不具合内容・原因・対策の類似検索)。

    **「〜のような不良」「同じ原因の類似事例」「この対策の前例」など、
    内容が曖昧・自然文の検索に使う。** 例: query="治具への固定不足でワークが動いた"

    機械・工程・期間など条件が明確な絞り込みは list_defect_reports のほうが正確。
    スコアが低い(0.8未満)結果しか無いときは、その旨を回答に添えること。

    Args:
        query: 検索したい内容の自然文
        top_k: 返す件数(既定5)
        machine, process: 指定時はその機械/工程の結果に絞る(表記は list_masters 参照)
    Returns:
        [{defect_id, part_name, machine_name, process, phenomenon, snippet, score}](score降順)
    """
    db = SessionLocal()
    try:
        fetch = top_k * 4 if (machine or process) else top_k
        results = rag.search(db, query, top_k=min(fetch, 40))
        out = []
        for s in results:
            if machine and s.get("machine_name") != machine:
                continue
            if process and s.get("process") != process:
                continue
            out.append(
                {
                    "defect_id": s["defect_id"],
                    "part_name": s.get("part_name"),
                    "machine_name": s.get("machine_name"),
                    "process": s.get("process"),
                    "phenomenon": s.get("phenomenon"),
                    "snippet": s["snippet"],
                    "score": s["score"],
                }
            )
            if len(out) >= top_k:
                break
        return out
    finally:
        db.close()


@mcp.tool
def get_defect_report(defect_id: str) -> dict:
    """報告書ID(KZ25-XXXX)を指定して不適合報告書の全項目を取得する。

    一覧・検索で見つけた報告書の詳細(不具合内容全文・原因・対策・費用など)を
    確認するときに使う。
    """
    db = SessionLocal()
    try:
        r = db.query(DefectReport).filter_by(defect_id=defect_id).first()
        if r is None:
            return {"error": f"{defect_id} は見つかりません"}
        return report_to_dict(r)
    finally:
        db.close()


@mcp.tool
def get_statistics(date_from: str | None = None, date_to: str | None = None) -> dict:
    """KPI(不良率・FPY・損失額)・現象パレート・機械/担当者/顧客/工程別・月次トレンド・
    4M/重要度内訳のダッシュボード統計を取得する。

    「全体で」「どの機械が多い?」「傾向は?」のような集計質問に使う。

    Args:
        date_from, date_to: 集計期間(YYYY-MM-DD、省略で全期間)
    """
    db = SessionLocal()
    try:
        return stats.statistics(db, date_from, date_to)
    finally:
        db.close()


@mcp.tool
def get_control_chart(months: int = 12) -> dict:
    """p管理図(月次不良率と管理限界 UCL/LCL)を取得する。

    工程が統計的管理状態にあるか、管理限界を超えた月がないかを見るときに使う。
    """
    db = SessionLocal()
    try:
        return stats.control_chart(db, months=months)
    finally:
        db.close()


@mcp.tool
def get_active_alerts() -> dict:
    """ルールベースの予兆アラート(不良率上昇・頻発パターン・再発)を取得する。

    「今注意すべきことは?」「アラートは出ている?」に使う。
    """
    db = SessionLocal()
    try:
        return stats.alerts(db)
    finally:
        db.close()


@mcp.tool
def list_masters(category: str | None = None) -> dict:
    """マスタ(ドロップダウン選択肢)の値一覧を取得する。

    **機械名・工程・客先・作業者・現象・要因の正確な表記を確認するために使う**
    (例: ユーザーが「CMX-800」と書いても実表記は "GENOS M560-V" かもしれない)。

    Args:
        category: customer / process / machine / operator / phenomenon / factor
                  (省略時は全カテゴリ)
    Returns:
        {カテゴリ: [{"name": 値, "usage_count": 使用件数}]}(有効な値のみ)
    """
    from models import MasterItem
    from routers.masters import CATEGORY_COLUMNS

    db = SessionLocal()
    try:
        cats = [category] if category else list(CATEGORY_COLUMNS.keys())
        out: dict[str, list] = {}
        for cat in cats:
            col = CATEGORY_COLUMNS.get(cat)
            if col is None:
                out[cat] = [{"error": f"不明なカテゴリ: {cat}"}]
                continue
            items = (
                db.query(MasterItem)
                .filter(MasterItem.category == cat, MasterItem.is_active.is_(True))
                .order_by(MasterItem.sort_order, MasterItem.name)
                .all()
            )
            out[cat] = [
                {
                    "name": m.name,
                    "usage_count": db.query(DefectReport).filter(col == m.name).count(),
                }
                for m in items
            ]
        return out
    finally:
        db.close()


@mcp.tool
def create_defect_report(
    occurrence_date: str,
    customer: str,
    process: str,
    machine_name: str,
    operator_name: str,
    part_number: str,
    part_name: str,
    production_count: int,
    defect_count: int,
    defect_description: str,
    phenomenon: str,
    severity: str,
    discoverer: str | None = None,
    good_condition: str | None = None,
    cause: str | None = None,
    factor: str | None = None,
    category_4m: str | None = None,
    countermeasure: str | None = None,
    notes: str | None = None,
) -> dict:
    """不適合報告書を新規登録する。defect_id は自動採番される。

    **ユーザーが明示的に「登録して」と依頼した場合のみ使うこと。**
    実行後は採番された defect_id を必ずユーザーに報告する。

    Args:
        occurrence_date: 発生日(YYYY-MM-DD)
        severity: critical / high / medium / low
        (他は docs/03 のフィールド定義に従う)
    """
    from datetime import date

    db = SessionLocal()
    try:
        data = {
            "occurrence_date": date.fromisoformat(occurrence_date),
            "customer": customer,
            "process": process,
            "machine_name": machine_name,
            "operator_name": operator_name,
            "part_number": part_number,
            "part_name": part_name,
            "production_count": production_count,
            "defect_count": defect_count,
            "defect_description": defect_description,
            "phenomenon": phenomenon,
            "severity": severity,
            "status": "open",
            "discoverer": discoverer,
            "good_condition": good_condition,
            "cause": cause,
            "factor": factor,
            "category_4m": category_4m,
            "countermeasure": countermeasure,
            "notes": notes,
        }
        report = create_report_core(db, data)
        return {"created": True, "defect_id": report.defect_id}
    except (ReportServiceError, ValueError) as exc:
        return {"created": False, "error": str(exc)}
    finally:
        db.close()


# update_defect_report で変更を許可するフィールド
_UPDATABLE = {
    "status",
    "severity",
    "countermeasure",
    "cause",
    "factor",
    "category_4m",
    "notes",
    "good_condition",
}


@mcp.tool
def update_defect_report(
    defect_id: str,
    status: str | None = None,
    severity: str | None = None,
    countermeasure: str | None = None,
    cause: str | None = None,
    factor: str | None = None,
    category_4m: str | None = None,
    notes: str | None = None,
    good_condition: str | None = None,
) -> dict:
    """既存の不適合報告書を部分更新する(渡した項目のみ)。

    **ユーザーが明示的に「更新して/完了にして」と依頼した場合のみ使うこと。**
    変更できるのは status(open/in_progress/completed)・severity・対策・原因・
    要因・4M分類・備考・良品状態のみ。実行後は変更内容をユーザーに報告する。
    """
    db = SessionLocal()
    try:
        r = db.query(DefectReport).filter_by(defect_id=defect_id).first()
        if r is None:
            return {"updated": False, "error": f"{defect_id} は見つかりません"}
        patch = {
            k: v
            for k, v in {
                "status": status,
                "severity": severity,
                "countermeasure": countermeasure,
                "cause": cause,
                "factor": factor,
                "category_4m": category_4m,
                "notes": notes,
                "good_condition": good_condition,
            }.items()
            if v is not None and k in _UPDATABLE
        }
        if not patch:
            return {"updated": False, "error": "更新する項目がありません"}
        update_report_core(db, r, patch)
        return {"updated": True, "defect_id": defect_id, "changed": list(patch.keys())}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# CAPA(是正・予防処置)・8D・ダイジェスト・類似検索(docs/10 A-1/A-2/A-3)
# ---------------------------------------------------------------------------


@mcp.tool
def get_similar_reports(defect_id: str, top_k: int = 3) -> dict:
    """指定した報告書に**似ている過去事例と「当時の対策」**を返す。

    「この不良の類似事例は?」「過去にどう対策した?」や、是正処置を検討する場面で使う。
    回答では類似事例を [KZ25-XXXX] 形式で引用すること。"""
    from services import rag
    from services.report_service import report_to_dict

    db = SessionLocal()
    try:
        base = db.query(DefectReport).filter_by(defect_id=defect_id).first()
        if base is None:
            return {"error": f"{defect_id} は見つかりません"}
        query = " ".join(filter(None, [base.phenomenon, base.defect_description, base.cause]))
        hits = [h for h in rag.search(db, query, top_k=top_k + 3) if h["defect_id"] != defect_id][:top_k]
        rows = {r.defect_id: r for r in db.query(DefectReport).filter(
            DefectReport.defect_id.in_([h["defect_id"] for h in hits])).all()}
        items = []
        for h in hits:
            r = rows.get(h["defect_id"])
            if r:
                items.append({"defect_id": r.defect_id, "phenomenon": r.phenomenon,
                              "machine_name": r.machine_name, "cause": r.cause,
                              "countermeasure": r.countermeasure, "score": h["score"]})
        return {"defect_id": defect_id, "items": items}
    finally:
        db.close()


@mcp.tool
def list_capa_actions(status: str | None = None, defect_id: str | None = None,
                      overdue: bool | None = None) -> dict:
    """CAPA(是正・予防処置)の一覧を取得する。

    「未完了の是正処置は?」「期限切れのCAPAは?」「KZ25-XXXXの処置状況は?」に使う。
    status: open / in_progress / effect_check / closed。overdue=True で期限超過のみ。"""
    from services import capa_service

    db = SessionLocal()
    try:
        items = capa_service.list_actions(db, status=status, defect_id=defect_id, overdue=overdue)
        return {"total": len(items), "items": items}
    finally:
        db.close()


@mcp.tool
def draft_capa_actions(defect_id: str) -> dict:
    """類似事例の「当時の対策」を根拠に、是正・予防処置のドラフト案を生成する(保存しない)。

    「対策案を考えて」「是正処置のドラフトを作って」で使う。採用・登録は
    ユーザーの明示依頼があったときに create_capa_action で行うこと。"""
    from services import capa_service
    from services.capa_service import CapaError

    db = SessionLocal()
    try:
        return capa_service.draft_actions(db, defect_id)
    except CapaError as e:
        return {"error": str(e)}
    finally:
        db.close()


@mcp.tool
def create_capa_action(defect_id: str, title: str, action_type: str = "corrective",
                       description: str | None = None, owner: str | None = None,
                       due_date: str | None = None) -> dict:
    """CAPA(是正・予防処置)を新規登録する。**ユーザーが明示的に依頼した場合のみ**使う。

    action_type: corrective(是正) / preventive(予防)。due_date: YYYY-MM-DD。"""
    from services import capa_service
    from services.capa_service import CapaError

    db = SessionLocal()
    try:
        a = capa_service.create(db, {"defect_id": defect_id, "title": title,
                                     "action_type": action_type, "description": description,
                                     "owner": owner, "due_date": due_date})
        return {"created": True, **capa_service.to_dict(a)}
    except CapaError as e:
        return {"created": False, "error": str(e)}
    finally:
        db.close()


@mcp.tool
def update_capa_action(capa_id: str, status: str | None = None, effect_note: str | None = None,
                       owner: str | None = None, due_date: str | None = None) -> dict:
    """CAPAの状態等を更新する。**ユーザーが明示的に依頼した場合のみ**使う。

    status: open / in_progress / effect_check / closed。closed には effect_note(効果確認)が必要。"""
    from services import capa_service
    from services.capa_service import CapaError

    db = SessionLocal()
    try:
        patch = {k: v for k, v in {"status": status, "effect_note": effect_note,
                                   "owner": owner, "due_date": due_date}.items() if v is not None}
        a = capa_service.update(db, capa_id, patch)
        return {"updated": True, **capa_service.to_dict(a)}
    except CapaError as e:
        return {"updated": False, "error": str(e)}
    finally:
        db.close()


@mcp.tool
def generate_8d_report(defect_id: str) -> dict:
    """報告書+CAPA+類似事例から8Dレポート(D1〜D8のMarkdown)を生成・保存して返す。

    「8Dレポートを作って」「8D形式でまとめて」で使う。生成後は内容の要約を回答し、
    画面で見せる場合は ui_open_report で詳細画面(8Dセクション)を開く。"""
    from services import capa_service
    from services.capa_service import CapaError

    db = SessionLocal()
    try:
        rep = capa_service.generate_8d(db, defect_id)
        return {"generated": True, "defect_id": defect_id, "content_md": rep.content_md,
                "ai_backend": rep.ai_backend}
    except CapaError as e:
        return {"generated": False, "error": str(e)}
    finally:
        db.close()


@mcp.tool
def generate_weekly_digest(days: int = 7) -> dict:
    """週次品質ダイジェスト(KPI前週比・重大案件・アラート+AI所見)を生成・保存して返す。

    「今週のまとめを作って」「週次レポートを出して」で使う。
    画面で見せる場合は ui_navigate(page="digests") を併用する。"""
    from services import digest as digest_service

    db = SessionLocal()
    try:
        d = digest_service.generate(db, days=days)
        return {"generated": True, "id": d.id, "period": f"{d.period_start}〜{d.period_end}",
                "content_md": d.content_md, "ai_backend": d.ai_backend}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# WebMCP: 画面操作ツール(AIアシスタント → ブラウザUIの直接コントロール)
# 実体は services/ui_control.py(REST /api/ui/* と同一コードパス)。
# 発動方針: 「見せて/出して/開いて/〜にして/〜で表示」など表示を変える意図が
# 読み取れる依頼では積極的に使う。純粋な質問(「何件?」等)はチャットで答える。
# 画面操作はデータを変更しない。
# ---------------------------------------------------------------------------


@mcp.tool
def ui_open_report(defect_id: str) -> dict:
    """報告書を画面で見たい・開きたいという依頼(「KZ25-0001を開いて」「詳細を見たい」等)で、
    ブラウザ画面を該当報告書の詳細ページへ遷移させる。データは変更しない。"""
    from services import ui_control

    return ui_control.open_report(defect_id)


@mcp.tool
def ui_navigate(
    page: str,
    q: str | None = None,
    machine: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    process: str | None = None,
    customer: str | None = None,
    operator: str | None = None,
    phenomenon: str | None = None,
    category_4m: str | None = None,
    sort: str | None = None,
    mode: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    months: int | None = None,
    sort_by: str | None = None,
    order: str | None = None,
) -> dict:
    """ブラウザのメイン画面を指定ページ・指定の表示条件に切り替える。

    **「〜を見せて/画面に出して」だけでなく「〜のサマリーにして」「〜の一覧を確認したい」
    「〜順で表示して」など、表示を変える意図が読み取れる依頼では積極的に使ってよい。**
    純粋な質問(「何件ある?」「原因は?」)にはチャットで答え、必要なら画面表示を提案する。

    page: dashboard | alerts | reports | chat | masters | digests(週次レポート) |
          capa(是正処置一覧。status/overdue/defect_id で絞り込み可) |
          analysis_machines | analysis_operators | analysis_customers | analysis_trends |
          ontology(業務Ontologyの対象・指標・関係の確認画面) | ontology_graph(Ontologyのグラフ)

    ページ別に使える表示条件:
    - reports: q / machine / severity / status / process / customer / operator /
      phenomenon / category_4m(Man|Machine|Material|Method) /
      sort("-occurrence_date"新しい順|"occurrence_date"|"-total_cost"損失大|"-defect_count") /
      mode("smart"=スマート検索。qに自然文) / date_from / date_to
    - dashboard: date_from / date_to(YYYY-MM-DD)
    - analysis_machines / analysis_operators / analysis_customers:
      date_from / date_to / sort_by(name|reports|defects|defect_rate|total_cost) / order(asc|desc)
    - analysis_trends: date_from / date_to / months(p管理図の月数)

    例: 「10〜12月のサマリーにして」→ page="dashboard", date_from="2025-10-01", date_to="2025-12-31"
        「『治具の固定が甘い』ような事例を画面で」→ page="reports", mode="smart", q="治具の固定が甘い"
    machine 等の表記は list_masters で確認してから渡すこと。データは変更しない。"""
    from services import ui_control

    return ui_control.navigate(
        page, q=q, machine=machine, severity=severity, status=status, process=process,
        customer=customer, operator=operator, phenomenon=phenomenon, category_4m=category_4m,
        sort=sort, mode=mode, date_from=date_from, date_to=date_to, months=months,
        sort_by=sort_by, order=order,
    )


@mcp.tool
def ui_new_report(
    occurrence_date: str | None = None,
    customer: str | None = None,
    process: str | None = None,
    machine_name: str | None = None,
    operator_name: str | None = None,
    part_number: str | None = None,
    part_name: str | None = None,
    phenomenon: str | None = None,
    severity: str | None = None,
    defect_description: str | None = None,
    cause: str | None = None,
    countermeasure: str | None = None,
    category_4m: str | None = None,
) -> dict:
    """「新規作成画面を開いて」「〜の内容で下書きを作って」という依頼で、
    報告書の新規作成画面(手動入力タブ)を開き、聞き取れた項目を下書き入力しておく。
    **保存はしない**(保存ボタンは利用者)。DB登録の明示依頼は create_defect_report を使う。"""
    from urllib.parse import urlencode

    from services import ui_bus

    fields = {
        "occurrence_date": occurrence_date, "customer": customer, "process": process,
        "machine_name": machine_name, "operator_name": operator_name,
        "part_number": part_number, "part_name": part_name, "phenomenon": phenomenon,
        "severity": severity, "defect_description": defect_description,
        "cause": cause, "countermeasure": countermeasure, "category_4m": category_4m,
    }
    params = {k: v for k, v in fields.items() if v not in (None, "")}
    path = "/reports/new" + ("?" + urlencode(params) if params else "")
    n = ui_bus.publish({"action": "navigate", "path": path,
                        "reason": "新規作成画面を開く" + ("(下書き入力済み)" if params else "")})
    if n == 0:
        return {"ok": False, "error": "ブラウザ画面が接続されていません(アプリを開いてもらってください)"}
    return {"ok": True, "path": path, "prefilled": list(params), "receivers": n}


@mcp.tool
def ui_edit_report(defect_id: str) -> dict:
    """「(報告書を)画面で編集したい」「編集モードにして」で、詳細画面を編集モードで開く。
    **入力・保存するのは利用者**。AIによる直接変更の明示依頼は update_defect_report。"""
    from services import ui_control

    return ui_control.command(
        "edit", {"defect_id": defect_id}, path=f"/reports/{defect_id}",
        reason=f"{defect_id} を編集モードで表示",
    )


@mcp.tool
def ui_run_4m_analysis(defect_id: str) -> dict:
    """「この報告書を4M分析して(画面で)見せて」で、詳細画面を開き
    画面上の「AIで4M分析」を実行して結果を表示させる。"""
    from services import ui_control

    return ui_control.command(
        "run_4m", {"defect_id": defect_id}, path=f"/reports/{defect_id}",
        reason=f"{defect_id} の4M分析を画面で実行",
    )


@mcp.tool
def ui_set_theme(mode: str) -> dict:
    """「ダークモードにして」「画面を明るくして」で、カラーテーマを切り替える。mode: dark | light"""
    from services import ui_control

    if mode not in ("dark", "light"):
        return {"ok": False, "error": "mode は dark または light"}
    return ui_control.command("set_theme", {"mode": mode}, reason=f"テーマを{mode}に切替")


# Streamable HTTP の ASGI アプリ(main.py で /mcp にマウント)
from services.ontology_mcp import register as register_ontology

register_ontology(mcp)
mcp_app = mcp.http_app(path="/")
