"""MCP サーバー defect-reports（06_AI設計書.md §2、04_API設計書.md §8）。

FastAPI に同居させ、main.py で /mcp に載せる（URL は /mcp/）。道具は DB を直接読む（自分の REST を HTTP で呼ばない）。
第3回は読み取りの5本だけ（書き込み・画面の操作・業務 Ontology は後の回）。
"""

from datetime import date
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from database import SessionLocal
from seed import MASTER_COLUMNS
from services import report_service

INSTRUCTIONS = """\
不適合報告書（KZ25-0001〜KZ25-0110 の110件）を読む道具です。報告書の値・件数は、そのターンでこの道具から取った値だけで答えてください。

推奨の順：
1. 機械・工程・客先などの名前は、まず list_masters で正しい表記を確かめる（似た名前に読み替えない）。
2. 条件がはっきりしていれば list_defect_reports（完全一致）、内容があいまいなら search_defect_reports。
3. 1件の中身は get_defect_report、件数・集計は get_statistics か list_defect_reports の total。

決まり：
- 絞り込みは完全一致。0件なら「該当なし」と答え、利用者の条件を黙って外さない。
- 名前は一字一句そのまま使う。list_masters に無い名前は「該当は存在しません」。1文字でも違う名前（例：GENOS M560-V と GENOS M660-V）に読み替えて件数や内容を答えない。
- 存在しない報告書番号を作らない。get_defect_report が error を返したら「見つからない」と答える。
- 件数は search_defect_reports の結果の数（上位だけを返すため）や、list_masters の usage_count で答えない。名前を確かめたあとも、件数は get_statistics か list_defect_reports の total で数える。
- この版の道具は読み取りだけ。報告書の登録・更新と、画面の操作はできない。画面で開くよう頼まれたら、できないと答え、報告書番号を [KZ25-XXXX] の形で書いてリンクから開けるようにする。
"""

mcp = FastMCP("defect-reports", instructions=INSTRUCTIONS)


def _parse_period(date_from: str | None, date_to: str | None) -> tuple[date | None, date | None, str | None]:
    """期間の文字列を日付にする。読めない・逆向きのときは理由を返す（0件の成功にしない）。"""
    try:
        start = date.fromisoformat(date_from) if date_from else None
        end = date.fromisoformat(date_to) if date_to else None
    except ValueError:
        return None, None, f"期間の日付が読めません（YYYY-MM-DD で指定してください）: date_from={date_from}, date_to={date_to}"
    if start and end and start > end:
        return None, None, f"date_from（{date_from}）が date_to（{date_to}）より後です"
    return start, end, None


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
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
    offset: Annotated[int, Field(ge=0)] = 0,
    sort: str = "-occurrence_date",
) -> dict:
    """条件がはっきりした絞り込みの一覧。件数は total で数える（items はそのページだけ）。

    いつ使うか：機械・工程・客先・作業者・現象・重大度・状態・4M・期間（発生日）で絞るとき。値はすべて完全一致で、AND で組む。
    引数の例：machine="a61nx"、phenomenon="表面キズ"、date_from="2025-09-01", date_to="2025-09-30"、
    severity は critical/high/medium/low、status は open/in_progress/completed、category_4m は Man/Machine/Material/Method。
    q は報告書番号・部品番号・部品名・不具合内容の部分一致。sort は -occurrence_date（既定）・-total_cost など。
    0件のとき：{"total": 0, "items": []} を返す。「該当なし」と答える。表記は list_masters で確かめる。
    返り値：{"total": 件数, "items": [要約（defect_id・発生日・客先・工程・機械・作業者・部品名・現象・重大度・状態・加工数・不適合数・defect_rate・total_cost）]}
    """
    start, end, error = _parse_period(date_from, date_to)
    if error:
        return {"error": error}
    with SessionLocal() as db:
        total, items = report_service.list_reports(
            db, limit=limit, offset=offset, sort=sort, q=q, date_from=start, date_to=end,
            machine=machine, process=process, customer=customer, operator=operator,
            phenomenon=phenomenon, severity=severity, status=status, category_4m=category_4m,
        )
        return {"total": total, "items": [report_service.report_summary(r) for r in items]}


@mcp.tool
def search_defect_reports(
    query: str,
    top_k: Annotated[int, Field(ge=1, le=50)] = 5,
    machine: str | None = None,
    process: str | None = None,
) -> list[dict]:
    """内容があいまいな類似事例を、キーワードで探す（上位 top_k 件だけを返す）。

    いつ使うか：「〜のような不良」「〜に似た事例」など、条件がはっきりしないとき。
    query の語（空白で区切る）のどれかを、不具合内容・原因・対策・部品名・現象から部分一致で探し、語の出てくる回数（score）の多い順に返す。
    引数の例：query="キズ 段取り"、query="バリ"、machine="汎用フライス"（あとから完全一致で絞る）。
    件数を答えるのには使わない（件数は list_defect_reports の total か get_statistics）。
    0件のとき：[] を返す。語を変えるか、list_defect_reports を使う。
    """
    with SessionLocal() as db:
        return report_service.search_reports(db, query, top_k=top_k, machine=machine, process=process)


@mcp.tool
def get_defect_report(defect_id: str) -> dict:
    """報告書番号（KZ25-XXXX）で1件の全項目を返す（defect_rate は小数4桁）。

    いつ使うか：報告書の中身（客先・機械・原因・対策・費用など）を述べるとき。前のターンの結果を使い回さず、毎回呼ぶ。
    引数の例：defect_id="KZ25-0043"
    無い番号のとき：{"error": "KZ25-9999 は見つかりません"} を返す。「見つからない」と答え、別の報告書の内容を述べない。
    """
    with SessionLocal() as db:
        report = report_service.get_report(db, defect_id)
        if report is None:
            return {"error": f"{defect_id} は見つかりません"}
        return report_service.report_to_dict(report)


@mcp.tool
def get_statistics(date_from: str | None = None, date_to: str | None = None) -> dict:
    """全体・期間の集計。件数・不適合数・加工数・不良率・損失の kpi、月別、現象のパレート、機械・作業者・工程・客先・4M・重大度別。

    いつ使うか：「何件？」「多い現象は？」「機械別の件数は？」など、件数や傾向を答えるとき。期間（発生日、両端を含む）を指定できる。
    引数の例：引数なし（全期間）、date_from="2025-11-01", date_to="2025-11-30"
    返り値の例：kpi.total_reports が件数。phenomenon_pareto の [{"name": "表面キズ", "count": 38, ...}] が現象別の件数。
    """
    start, end, error = _parse_period(date_from, date_to)
    if error:
        return {"error": error}
    with SessionLocal() as db:
        return report_service.statistics(db, start, end)


@mcp.tool
def list_masters(category: str | None = None) -> dict:
    """名前の正しい表記と使用件数（有効な値だけ）。

    いつ使うか：機械・工程・客先・作業者・現象・要因の名前を、絞り込みに使う前に確かめるとき。似た名前に読み替えない。
    category は customer・process・machine・operator・phenomenon・factor のどれか（省略で6種類すべて）。
    返り値：{種類: [{"name": 名前, "usage_count": 報告書の件数}]}。無い名前は「該当は存在しません」と答える。
    usage_count は表記を選ぶための目安。件数を答えるときは、この値を使わず get_statistics か list_defect_reports の total で数える。
    1文字でも違う名前（例：GENOS M560-V と GENOS M660-V）は別のもの。読み替えて、別のものの件数を答えない。
    """
    if category is not None and category not in MASTER_COLUMNS:
        return {"error": f"category は {', '.join(MASTER_COLUMNS)} のどれかです: {category}"}
    with SessionLocal() as db:
        masters = report_service.masters_with_usage(db)
    categories = [category] if category else list(MASTER_COLUMNS)
    return {
        name: [{"name": m["name"], "usage_count": m["usage_count"]} for m in masters[name] if m["is_active"]]
        for name in categories
    }
