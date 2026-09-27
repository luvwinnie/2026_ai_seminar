"""API 結合テスト。

一時DBに対して実行し、開発用データには触れない。
埋め込みは EMBEDDINGS=off で無効化し、キーワード検索でテストする(モデルDL不要・高速)。
ANTHROPIC_API_KEY は未設定を前提とする。
"""
import json
import os
import sys
import tempfile
from pathlib import Path

# --- テスト用の環境を import 前に設定する ---
BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_DIR.parents[1]  # example_app/
sys.path.insert(0, str(BACKEND_DIR))

_tmpdir = tempfile.mkdtemp(prefix="defectreport_test_")
os.environ["DB_PATH"] = str(Path(_tmpdir) / "test.db")
os.environ["DATA_CSV"] = str(APP_ROOT / "data" / "defect_reports.csv")
os.environ["CHROMA_PATH"] = str(Path(_tmpdir) / "chroma")
os.environ["EMBEDDINGS"] = "off"  # キーワード検索に固定
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("OPENCODE_URL", None)  # チャット/抽出は未設定(503 経路をテスト)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

XLSX_SAMPLE = APP_ROOT / "data" / "forms_xlsx" / "KZ25-0001.xlsx"


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:  # with 文で startup(シード)を発火
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["reports"] > 0
    assert body["anthropic_configured"] is False
    assert body["vector_search"] == "keyword"


def test_reports_list(client):
    r = client.get("/api/reports?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 0
    assert len(body["items"]) <= 10
    # defect_rate が計算されている
    assert "defect_rate" in body["items"][0]


def test_reports_filter(client):
    r = client.get("/api/reports?severity=high&limit=5")
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["severity"] == "high"


def test_report_crud(client):
    # 作成(defect_id 自動採番)
    payload = {
        "occurrence_date": "2025-09-01",
        "customer": "Z社",
        "process": "旋盤",
        "machine_name": "QUICK TURN 250MSY",
        "operator_name": "テスト作業者",
        "part_number": "9999-000000-00",
        "part_name": "テスト部品",
        "production_count": 100,
        "defect_count": 4,
        "defect_description": "テスト不具合",
        "phenomenon": "寸法公差外れ",
        "severity": "medium",
    }
    r = client.post("/api/reports", json=payload)
    assert r.status_code == 201
    created = r.json()
    defect_id = created["defect_id"]
    assert defect_id.startswith("KZ25-")
    assert created["defect_rate"] == 0.04  # 4 / 100

    # 取得
    r = client.get(f"/api/reports/{defect_id}")
    assert r.status_code == 200
    assert r.json()["part_name"] == "テスト部品"

    # 更新
    r = client.put(f"/api/reports/{defect_id}", json={"status": "in_progress"})
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"

    # 削除
    r = client.delete(f"/api/reports/{defect_id}")
    assert r.status_code == 204

    # 削除後は 404
    r = client.get(f"/api/reports/{defect_id}")
    assert r.status_code == 404


def test_dashboard_statistics(client):
    r = client.get("/api/dashboard/statistics")
    assert r.status_code == 200
    body = r.json()
    # KPI 形状
    for key in (
        "total_reports",
        "total_defects",
        "total_production",
        "defect_rate",
        "fpy",
        "total_cost",
        "recurrence_rate",
        "open_count",
    ):
        assert key in body["kpi"]
    # 各内訳
    assert isinstance(body["monthly_trend"], list)
    assert isinstance(body["pareto_phenomenon"], list)
    assert isinstance(body["by_machine"], list)
    assert isinstance(body["by_4m"], list)
    assert isinstance(body["by_severity"], list)
    # パレートの累積比率は単調増加
    if body["pareto_phenomenon"]:
        cums = [p["cumulative_ratio"] for p in body["pareto_phenomenon"]]
        assert cums == sorted(cums)


def test_control_chart(client):
    r = client.get("/api/dashboard/control-chart?months=12")
    assert r.status_code == 200
    body = r.json()
    assert "p_bar" in body
    assert isinstance(body["items"], list)
    if body["items"]:
        item = body["items"][0]
        for key in ("period", "n", "defects", "p", "ucl", "lcl"):
            assert key in item
        # LCL は 0 でクリップ
        assert item["lcl"] >= 0


def test_alerts(client):
    r = client.get("/api/analysis/alerts")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    for item in body["items"]:
        assert item["level"] in ("critical", "warning", "info")
        assert "title" in item
        assert "message" in item


def test_ingest_xlsx_no_key(client):
    """xlsx はキー無しでもセル抽出のみで返る(confidence: medium + warning)。"""
    assert XLSX_SAMPLE.exists(), f"サンプル帳票が見つかりません: {XLSX_SAMPLE}"
    with open(XLSX_SAMPLE, "rb") as f:
        r = client.post(
            "/api/ingest/upload",
            files={
                "file": (
                    "KZ25-0001.xlsx",
                    f.read(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] == "medium"
    assert body["warnings"]  # キー未設定の警告が付く
    extracted = body["extracted"]
    # ラベル走査で主要項目が抽出できている
    # 期待値は生成データ(CSV)の先頭行から取る(データ再生成に追随)
    import csv as _csv

    with open(XLSX_SAMPLE.parent.parent / "defect_reports.csv", encoding="utf-8") as f:
        first = next(_csv.DictReader(f))
    assert extracted.get("customer") == first["customer"]
    assert extracted.get("machine_name") == first["machine_name"]
    assert extracted.get("production_count") == int(first["production_count"])
    assert extracted.get("defect_count") == int(first["defect_count"])
    assert extracted.get("material_cost") == float(first["material_cost"])


def test_ingest_pdf_no_key_returns_503(client):
    """pdf/画像はキー未設定で 503。"""
    r = client.post(
        "/api/ingest/upload",
        files={"file": ("scan.pdf", b"%PDF-1.4 dummy", "application/pdf")},
    )
    assert r.status_code == 503


def test_chat_non_streaming_returns_503_without_key(client):
    r = client.post("/api/chat", json={"message": "旋盤のバリ不良について教えて", "history": []})
    assert r.status_code == 503


def test_chat_stream_emits_sources_without_key(client):
    """SSE は 200 を返し、sources と error(キー未設定)を含む。"""
    r = client.post("/api/chat/stream", json={"message": "バリ", "history": []})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    text = r.text
    assert "event: sources" in text
    # キー未設定なので error イベントで終わる
    assert "event: error" in text


# --- マスタ管理 ---


def _find_master(client, category: str, name: str) -> dict | None:
    r = client.get(f"/api/masters/{category}")
    assert r.status_code == 200
    return next((m for m in r.json() if m["name"] == name), None)


def _report_payload(**overrides) -> dict:
    base = {
        "occurrence_date": "2025-09-15",
        "customer": "翠峰重工業",
        "process": "旋盤",
        "machine_name": "QUICK TURN 250MSY",
        "operator_name": "テスト作業者",
        "part_number": "9999-000000-01",
        "part_name": "テスト部品",
        "production_count": 100,
        "defect_count": 3,
        "defect_description": "テスト不具合",
        "phenomenon": "寸法公差外れ",
        "severity": "medium",
    }
    base.update(overrides)
    return base


def test_masters_list_seeded(client):
    """全カテゴリ一覧: customer に 翠峰重工業 が居り、usage_count>0。"""
    r = client.get("/api/masters")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"customer", "process", "machine", "operator", "phenomenon", "factor"}
    a = next((m for m in body["customer"] if m["name"] == "翠峰重工業"), None)
    assert a is not None
    assert a["usage_count"] > 0  # シードデータで 翠峰重工業 は使用中
    # operator は既定語彙が無くても DISTINCT で投入されている
    assert len(body["operator"]) > 0


def test_masters_invalid_category_404(client):
    assert client.get("/api/masters/unknown").status_code == 404
    assert client.post("/api/masters/unknown", json={"name": "x"}).status_code == 404


def test_masters_create_and_duplicate(client):
    r = client.post("/api/masters/customer", json={"name": "新規客先ABC"})
    assert r.status_code == 201
    assert r.json()["name"] == "新規客先ABC"
    assert r.json()["usage_count"] == 0
    # 重複(前後空白・大文字小文字無視)は 409
    dup = client.post("/api/masters/customer", json={"name": "  新規客先abc  "})
    assert dup.status_code == 409


def test_masters_rename_propagates(client):
    """リネームで既存報告書の customer が変わり、updated_reports が件数と一致する。"""
    # 一意な客先で2件作成 → マスタ自動登録
    client.post("/api/reports", json=_report_payload(customer="リネーム元社"))
    client.post("/api/reports", json=_report_payload(customer="リネーム元社"))

    master = _find_master(client, "customer", "リネーム元社")
    assert master is not None

    r = client.put(f"/api/masters/customer/{master['id']}", json={"name": "リネーム先社"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "リネーム先社"
    assert body["updated_reports"] == 2

    # 既存報告書が新名称へ伝播している
    listed = client.get("/api/reports", params={"q": "テスト部品", "limit": 500}).json()
    renamed = [x for x in listed["items"] if x["customer"] == "リネーム先社"]
    assert len(renamed) == 2
    assert not [x for x in listed["items"] if x["customer"] == "リネーム元社"]


def test_masters_delete_in_use_409_unused_204(client):
    # 使用中(翠峰重工業)は削除できず 409
    a = _find_master(client, "customer", "翠峰重工業")
    assert a is not None
    assert client.delete(f"/api/masters/customer/{a['id']}").status_code == 409

    # 未使用マスタは物理削除 204
    created = client.post("/api/masters/factor", json={"name": "未使用要因XYZ"}).json()
    assert client.delete(f"/api/masters/factor/{created['id']}").status_code == 204
    assert _find_master(client, "factor", "未使用要因XYZ") is None


def test_report_create_autoregisters_master(client):
    """報告書作成で新しい客先がマスタへ自動登録される。"""
    assert _find_master(client, "customer", "自動登録客先QQQ") is None
    r = client.post("/api/reports", json=_report_payload(customer="自動登録客先QQQ"))
    assert r.status_code == 201
    m = _find_master(client, "customer", "自動登録客先QQQ")
    assert m is not None
    assert m["is_active"] is True


# ---- OpenCode 全面移行に伴う追加テスト ----


def test_health_chat_backend_none(client):
    assert client.get("/health").json()["chat_backend"] == "none"


def test_chat_503_message(client):
    r = client.post("/api/chat", json={"message": "test"})
    assert r.status_code == 503
    assert "OPENCODE_URL" in r.json()["detail"]


def test_ingest_pdf_503_message(client):
    pdf = APP_ROOT / "data" / "forms_pdf" / "KZ25-0001.pdf"
    r = client.post("/api/ingest/upload", files={"file": ("a.pdf", pdf.read_bytes(), "application/pdf")})
    assert r.status_code == 503
    assert "OPENCODE_URL" in r.json()["detail"]


def test_mcp_list_defect_reports_filters(client):
    from services.mcp_server import list_defect_reports

    res = list_defect_reports(machine="TSL-550", limit=5)
    assert res["total"] > 0
    assert all(i["machine_name"] == "TSL-550" for i in res["items"])
    assert "defect_rate" in res["items"][0]


def test_mcp_list_masters(client):
    from services.mcp_server import list_masters

    res = list_masters(category="machine")
    names = [m["name"] for m in res["machine"]]
    assert "TSL-550" in names
    assert all(m["usage_count"] >= 0 for m in res["machine"])


def test_mcp_update_defect_report(client):
    from services.mcp_server import get_defect_report, update_defect_report

    before = get_defect_report("KZ25-0001")
    res = update_defect_report("KZ25-0001", status="in_progress")
    assert res["updated"] is True and res["changed"] == ["status"]
    assert get_defect_report("KZ25-0001")["status"] == "in_progress"
    # 復元
    update_defect_report("KZ25-0001", status=before["status"])
    # 更新項目なしはエラー
    assert update_defect_report("KZ25-0001")["updated"] is False


def test_mcp_create_defect_report(client):
    from services.mcp_server import create_defect_report

    res = create_defect_report(
        occurrence_date="2026-07-05",
        customer="MCPテスト社",
        process="旋盤",
        machine_name="QUICK TURN 250MSY",
        operator_name="MCP検証",
        part_number="0000-2",
        part_name="MCPテスト部品",
        production_count=3,
        defect_count=1,
        defect_description="MCP経由の登録テスト",
        phenomenon="寸法公差外れ",
        severity="low",
    )
    assert res["created"] is True and res["defect_id"].startswith("KZ25-")
    # 後始末(REST 経由で削除)
    assert client.delete(f"/api/reports/{res['defect_id']}").status_code == 204


def test_opencode_parse_json_text():
    from services.opencode_client import _parse_json_text

    assert _parse_json_text('{"a": 1}') == {"a": 1}
    assert _parse_json_text('前置きです\n```json\n{"a": {"b": 2}}\n```\n以上') == {"a": {"b": 2}}
    import pytest as _pytest

    with _pytest.raises(ValueError):
        _parse_json_text("JSONなし")


# ---- チャット履歴の永続化 ----


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """SSE テキストを [(event, data_dict), ...] にパースする。"""
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        event = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if event:
            events.append((event, json.loads(data) if data else {}))
    return events


def _first(events, name):
    return next(d for e, d in events if e == name)


def test_chat_stream_persists_session(client):
    """新規セッション: session→sources→error の順、user メッセージが保存され一覧に載る。"""
    r = client.post("/api/chat/stream", json={"message": "旋盤のバリ不良について教えて", "history": []})
    assert r.status_code == 200
    events = _parse_sse(r.text)
    types = [e for e, _ in events]
    # session が先頭・sources より前・error で終わる(OPENCODE 未設定)
    assert types[0] == "session"
    assert types.index("session") < types.index("sources") < types.index("error")

    sess = _first(events, "session")
    sid = sess["id"]
    assert isinstance(sid, int)
    assert sess["title"]  # 先頭30文字由来

    # 一覧に載り、message_count>=1(error 経路でも user は保存)
    listed = client.get("/api/chat/sessions").json()
    mine = next((s for s in listed if s["id"] == sid), None)
    assert mine is not None
    assert mine["message_count"] >= 1

    # 詳細に user メッセージが入っている
    detail = client.get(f"/api/chat/sessions/{sid}").json()
    assert detail["session"]["id"] == sid
    assert any(
        m["role"] == "user" and "旋盤のバリ不良" in m["content"] for m in detail["messages"]
    )

    # 削除 → 204 → 以後 404
    assert client.delete(f"/api/chat/sessions/{sid}").status_code == 204
    assert client.get(f"/api/chat/sessions/{sid}").status_code == 404


def test_chat_stream_reuses_session(client):
    """同一 session_id を渡すと同じセッションに追記される。"""
    r1 = client.post("/api/chat/stream", json={"message": "最初の質問です"})
    sid = _first(_parse_sse(r1.text), "session")["id"]

    r2 = client.post("/api/chat/stream", json={"message": "2つ目の質問です", "session_id": sid})
    sid2 = _first(_parse_sse(r2.text), "session")["id"]
    assert sid2 == sid

    detail = client.get(f"/api/chat/sessions/{sid}").json()
    users = [m for m in detail["messages"] if m["role"] == "user"]
    assert len(users) == 2

    client.delete(f"/api/chat/sessions/{sid}")


def test_chat_session_not_found(client):
    assert client.get("/api/chat/sessions/999999").status_code == 404
    assert client.delete("/api/chat/sessions/999999").status_code == 404
