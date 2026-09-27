"""ハイブリッド検索(services/hybrid.py)と WebMCP UIブリッジの単体テスト。

test_api.py と同様に一時DB + EMBEDDINGS=off で実行する
(BM25 は埋め込み無しで動くことが要件のひとつ)。
"""
import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_DIR.parents[1]
sys.path.insert(0, str(BACKEND_DIR))

_tmpdir = tempfile.mkdtemp(prefix="defectreport_hybrid_test_")
os.environ.setdefault("DB_PATH", str(Path(_tmpdir) / "test.db"))
os.environ.setdefault("DATA_CSV", str(APP_ROOT / "data" / "defect_reports.csv"))
os.environ.setdefault("CHROMA_PATH", str(Path(_tmpdir) / "chroma"))
os.environ["EMBEDDINGS"] = "off"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from services import hybrid, rag, ui_bus  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture()
def db(client):
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


# --- トークン化・同義語 ---

def test_tokenize_fallback_bigram():
    toks = hybrid.tokenize("寸法公差外れが発生 NC旋盤A")
    assert "寸法" in toks or "寸法公差外れ" in toks  # Sudachi 有無どちらでも成立
    assert "nc" in toks  # 英数は正規化して単語単位


def test_expand_query_synonyms():
    expanded = hybrid.expand_query("キズの対策を教えて")
    assert "傷" in expanded
    assert "再発防止策" in expanded


def test_expand_query_no_hit_returns_original():
    q = "特に該当のない文章です"
    assert hybrid.expand_query(q) == q


# --- ファセット層 ---

def test_facet_extraction_and_penalty(db):
    idx = hybrid._get_index(db)
    machines = sorted(idx.machines)
    assert machines, "シードデータに機械名があるはず"
    target = machines[0]
    facets = hybrid.extract_query_facets(f"{target}の不良を教えて", machines, sorted(idx.processes))
    assert facets.get("machine") == target

    class Row:  # 最小のダミー行
        machine_name = target
        process = None
        severity = None
        category_4m = None

    class OtherRow:
        machine_name = "存在しない機械Z"
        process = None
        severity = None
        category_4m = None

    assert hybrid.facet_multiplier(facets, Row()) > 1.0
    assert hybrid.facet_multiplier(facets, OtherRow()) < 1.0
    # 属性が読めない文書は中立
    class NeutralRow:
        machine_name = None
        process = None
        severity = None
        category_4m = None

    assert hybrid.facet_multiplier(facets, NeutralRow()) == 1.0


# --- BM25 / 融合検索 ---

def test_bm25_search_returns_results_without_embeddings(db):
    out = rag.search(db, "寸法公差外れの対策", top_k=5)
    assert out, "埋め込み無しでも BM25 で結果が返る"
    assert out[0]["search_mode"] == "bm25"
    assert out[0]["defect_id"].startswith("KZ25-")


def test_search_self_retrieval(db):
    """報告書本文の一文をクエリにすると、その報告書が上位に来る(自己検索)。"""
    from models import DefectReport

    row = db.query(DefectReport).filter(DefectReport.defect_description.isnot(None)).first()
    sentence = (row.defect_description or "")[:40]
    out = rag.search(db, sentence, top_k=5)
    assert row.defect_id in [o["defect_id"] for o in out]


def test_facet_changes_ranking(db):
    """機械名を明示すると、その機械の報告書が優遇される。"""
    from models import DefectReport

    row = db.query(DefectReport).filter(DefectReport.machine_name.isnot(None)).first()
    out = rag.search(db, f"{row.machine_name}の{row.phenomenon}", top_k=5)
    assert out
    assert out[0]["machine_name"] == row.machine_name


def test_invalidate_rebuilds_index(db):
    idx1 = hybrid._get_index(db)
    hybrid.invalidate()
    idx2 = hybrid._get_index(db)
    assert idx2 is not idx1
    assert idx2.n == idx1.n


# --- WebMCP: UI イベントバスとツール ---

def test_ui_bus_publish_subscribe():
    q = ui_bus.subscribe()
    try:
        n = ui_bus.publish({"action": "navigate", "path": "/dashboard"})
        assert n >= 1
        ev = q.get(timeout=1)
        assert ev["path"] == "/dashboard"
    finally:
        ui_bus.unsubscribe(q)


def test_ui_tools_require_browser():
    """購読者ゼロのときはエラーを返す(ブラウザ未接続の検知)。"""
    from services.mcp_server import ui_navigate, ui_open_report

    nav = ui_navigate.fn if hasattr(ui_navigate, "fn") else ui_navigate
    opn = ui_open_report.fn if hasattr(ui_open_report, "fn") else ui_open_report
    assert nav(page="dashboard")["ok"] is False
    q = ui_bus.subscribe()
    try:
        res = opn(defect_id="KZ25-0001")
        assert res["ok"] is True and res["path"] == "/reports/KZ25-0001"
        assert q.get(timeout=1)["path"] == "/reports/KZ25-0001"
        res2 = nav(page="reports", machine="NC旋盤A")
        assert res2["ok"] is True and res2["path"].startswith("/reports?")
        bad = nav(page="unknown_page")
        assert bad["ok"] is False
    finally:
        ui_bus.unsubscribe(q)


def test_ui_events_sse_generator(client):
    """SSE 応答の中身をジェネレータ直駆動で検証する。

    TestClient は無限ストリームの早期クローズを扱えない(クローズ時にドレインして
    ハングする)ため、HTTP 経由ではなくレスポンスの body_iterator を直接進める。
    ブラウザ経由の実挙動は e2e/test_chat_webmcp.py で検証済み。
    """
    from routers.ui import ui_events

    resp = ui_events()
    assert resp.media_type == "text/event-stream"
    # ui_events() 呼び出し時点で subscribe 済みなので、この publish は取りこぼさない
    n = ui_bus.publish({"action": "navigate", "path": "/alerts"})
    assert n >= 1
    import asyncio

    async def read_two():
        gen = resp.body_iterator  # 同期ジェネレータは Starlette が async 化している
        first = await gen.__anext__()
        second = await gen.__anext__()
        await gen.aclose()  # finally 節で unsubscribe される
        return first, second

    first, second = asyncio.run(read_two())
    assert "connected" in first
    assert "event: ui" in second and "/alerts" in second


# --- スマート検索 REST(GET /api/reports/search) ---

def test_smart_search_endpoint(client):
    r = client.get("/api/reports/search", params={"q": "キズの対策"})
    assert r.status_code == 200
    body = r.json()
    assert body["search_mode"] in ("bm25", "hybrid", "keyword")
    assert body["items"], "結果が返る"
    assert body["items"][0]["defect_id"].startswith("KZ25-")
    assert "score" in body["items"][0] and "snippet" in body["items"][0]


def test_smart_search_machine_postfilter(client, db):
    from models import DefectReport

    row = db.query(DefectReport).filter(DefectReport.machine_name.isnot(None)).first()
    r = client.get(
        "/api/reports/search",
        params={"q": row.phenomenon or "不良", "machine": row.machine_name, "top_k": 5},
    )
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["machine_name"] == row.machine_name


def test_smart_search_requires_q(client):
    assert client.get("/api/reports/search").status_code == 422


def test_reports_list_new_filters(client, db):
    from models import DefectReport

    row = db.query(DefectReport).first()
    r = client.get("/api/reports", params={"customer": row.customer, "operator": row.operator_name})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert item["customer"] == row.customer


# --- ui_navigate の新パラメータ(スマート検索・フィルタ・ソート) ---

def test_ui_navigate_smart_and_filters():
    from services.mcp_server import ui_navigate

    nav = ui_navigate.fn if hasattr(ui_navigate, "fn") else ui_navigate
    q = ui_bus.subscribe()
    try:
        res = nav(page="reports", mode="smart", q="治具の固定が甘い")
        assert res["ok"] and "mode=smart" in res["path"] and "q=" in res["path"]
        res2 = nav(page="reports", customer="翠峰重工業", category_4m="Method", sort="-total_cost")
        assert res2["ok"]
        assert "customer=" in res2["path"] and "category_4m=Method" in res2["path"] and "sort=" in res2["path"]
        res3 = nav(page="analysis_machines", sort_by="total_cost", order="desc", date_from="2025-10-01")
        assert res3["ok"] and "sort_by=total_cost" in res3["path"]
    finally:
        ui_bus.unsubscribe(q)


# --- ui_control / REST 画面操作(全ページの path 組み立て) ---

def test_ui_control_all_pages():
    from services import ui_control

    cases = {
        "dashboard": {"date_from": "2025-10-01", "date_to": "2025-12-31"},
        "alerts": {},
        "reports": {"machine": "GENOS M560-V", "severity": "high", "sort": "-total_cost"},
        "chat": {},
        "masters": {},
        "analysis_machines": {"sort_by": "total_cost", "order": "desc"},
        "analysis_operators": {"date_from": "2025-04-01"},
        "analysis_customers": {},
        "analysis_trends": {"months": 6},
    }
    for page, params in cases.items():
        path = ui_control.build_path(page, params)
        assert path.startswith(ui_control.UI_PAGES[page])
        for k, v in params.items():
            assert f"{k}=" in path, f"{page}: {k} が付与されない"
    # 未知ページ・未許可パラメータ
    import pytest as _pytest

    with _pytest.raises(ValueError):
        ui_control.build_path("unknown", {})
    assert "bogus" not in ui_control.build_path("reports", {"bogus": "x", "q": "a"})


def test_ui_rest_endpoints(client):
    q = ui_bus.subscribe()
    try:
        r = client.post("/api/ui/navigate", json={"page": "dashboard", "params": {"date_from": "2025-10-01"}})
        assert r.status_code == 200 and r.json()["ok"]
        assert q.get(timeout=1)["path"].startswith("/dashboard?date_from=")
        r2 = client.post("/api/ui/open_report/KZ25-0001")
        assert r2.json()["path"] == "/reports/KZ25-0001"
        q.get(timeout=1)
        r3 = client.post("/api/ui/command", json={"name": "set_theme", "params": {"mode": "dark"}})
        assert r3.json()["ok"]
        ev = q.get(timeout=1)
        assert ev["name"] == "set_theme"
        # 未知ページはエラー
        r4 = client.post("/api/ui/navigate", json={"page": "nope"})
        assert r4.json()["ok"] is False
    finally:
        ui_bus.unsubscribe(q)
