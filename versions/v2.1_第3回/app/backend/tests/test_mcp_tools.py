"""MCP の道具を LLM を通さずに呼ぶ（07_試験・運用仕様書.md §2.3 AC-v20-05・06 ほか）。期待値は data/defect_reports.csv から数えた値。"""

import asyncio

from fastmcp import Client

from services.mcp_server import mcp

READ_TOOLS = {"list_defect_reports", "search_defect_reports", "get_defect_report", "get_statistics", "list_masters"}


def call(name: str, args: dict | None = None):
    async def run():
        async with Client(mcp) as c:
            return await c.call_tool(name, args or {}, raise_on_error=False)
    return asyncio.run(run())


def test_AC_v20_05_tool_count(client):
    async def run():
        async with Client(mcp) as c:
            return await c.list_tools()
    tools = asyncio.run(run())
    # 第3回は読み取りの5本だけ
    assert len(tools) == 5
    assert {t.name for t in tools} == READ_TOOLS


def test_AC_v20_06_get_defect_report(client):
    data = call("get_defect_report", {"defect_id": "KZ25-0043"}).data
    assert data["machine_name"] == "a61nx"
    assert data["defect_rate"] == 0.25
    assert data["customer"] == "翠峰重工業"
    assert data["phenomenon"] == "表面キズ"


def test_AC_v20_06_not_found(client):
    assert call("get_defect_report", {"defect_id": "KZ25-9999"}).data == {"error": "KZ25-9999 は見つかりません"}


def test_AC_v20_06_list_total(client):
    data = call("list_defect_reports", {"phenomenon": "表面キズ", "limit": 1}).data
    assert data["total"] == 38
    assert len(data["items"]) == 1


def test_AC_v20_06_statistics(client):
    kpi = call("get_statistics").data["kpi"]
    assert kpi["total_reports"] == 110
    assert kpi["defect_units"] == 1829
    assert kpi["production_units"] == 10460
    assert kpi["total_loss"] == 36445731
    assert kpi["defect_rate"] == 0.1749


def test_AC_v20_03_count_by_statistics(client):
    # 「表面キズは何件？」は集計の道具で数える（38件）
    pareto = call("get_statistics").data["phenomenon_pareto"]
    assert pareto[0] == {"name": "表面キズ", "count": 38, "ratio": 0.3455, "cumulative_ratio": 0.3455}
    assert [p["name"] for p in pareto[:3]] == ["表面キズ", "バリ残り", "穴位置ずれ"]


def test_AC_v20_03_search_is_top_k_only(client):
    # 検索の道具は上位だけを返すので、件数を数えるのには使えない（「バリ」を含む報告書は14件）
    results = call("search_defect_reports", {"query": "バリ"}).data
    assert len(results) == 5
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert all("バリ" in r["snippet"] for r in results)
    assert len(call("search_defect_reports", {"query": "バリ", "top_k": 50}).data) == 14


def test_AC_v20_03_search_no_match(client):
    assert call("search_defect_reports", {"query": "存在しない語XYZ"}).data == []


def test_AC_v20_06_list_and_condition(client):
    # UC-2：汎用フライスのバリ残りは7件（AND で絞る）
    data = call("list_defect_reports", {"machine": "汎用フライス", "phenomenon": "バリ残り"}).data
    assert data["total"] == 7
    assert [i["defect_id"] for i in data["items"]] == [
        "KZ25-0099", "KZ25-0096", "KZ25-0094", "KZ25-0073", "KZ25-0050", "KZ25-0035", "KZ25-0024",
    ]


def test_AC_v20_12_zero_is_not_error(client):
    # マスタにはあるが報告の無い機械は0件（失敗ではない）
    result = call("list_defect_reports", {"machine": "GENOS M560-V"})
    assert not result.is_error
    assert result.data == {"total": 0, "items": []}


def test_AC_v20_12_bad_period_is_error(client):
    data = call("list_defect_reports", {"date_from": "2025-10-01", "date_to": "2025-09-01"}).data
    assert "error" in data
    assert "error" in call("get_statistics", {"date_from": "2025-13-01"}).data


def test_AC_v20_12_limit_out_of_range(client):
    assert call("list_defect_reports", {"limit": 101}).is_error
    assert call("list_defect_reports", {"limit": 0}).is_error


def test_AC_v20_06_statistics_period(client):
    kpi = call("get_statistics", {"date_from": "2025-11-01", "date_to": "2025-11-30"}).data["kpi"]
    assert kpi["total_reports"] == 23
    assert kpi["defect_units"] == 365


def test_AC_v20_09_list_masters(client):
    data = call("list_masters", {"category": "machine"}).data
    names = {m["name"]: m["usage_count"] for m in data["machine"]}
    assert names["a61nx"] == 3
    assert "TXG-9000" not in names
    assert set(call("list_masters").data) == {"customer", "process", "machine", "operator", "phenomenon", "factor"}
    assert "error" in call("list_masters", {"category": "unknown"}).data
