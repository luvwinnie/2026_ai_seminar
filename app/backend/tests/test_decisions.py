"""判断モデルによる強化(services/decisions.py)のテスト。

判断モデルは呼ばない(decision_client.decide を差し替える)。ネットワーク・費用なしで、
① 検索の並べ替え ② 質問の振り分け ③ 引用の確かめ ④ 読み取りの確かめ と、
検索・チャット・取込へのつなぎ方(失敗しても止まらないこと、確信度の決め方)を確かめる。
"""
import base64
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_DIR.parents[1]
sys.path.insert(0, str(BACKEND_DIR))

_tmpdir = tempfile.mkdtemp(prefix="defectreport_decisions_")
os.environ.setdefault("DB_PATH", str(Path(_tmpdir) / "test.db"))
os.environ.setdefault("DATA_CSV", str(APP_ROOT / "data" / "defect_reports.csv"))
os.environ.setdefault("CHROMA_PATH", str(Path(_tmpdir) / "chroma"))
os.environ.setdefault("EMBEDDINGS", "off")
os.environ.pop("OPENCODE_URL", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import DefectReport  # noqa: E402
from services import decision_client as dc  # noqa: E402
from services import decisions, rag  # noqa: E402

CALLS: list = []
NOUL: dict = {}        # state の中の文字 → noul の値(無ければ 0.1)
CHOICE: dict = {}      # 質問 → (選択肢, 確率)
FAIL = {"on": False}


def fake_decide(state, questions, retries=3, **kw):
    if FAIL["on"]:
        raise dc.DecisionError("テスト用の失敗")
    CALLS.append({"state": state, "questions": questions, "model": kw.get("model")})
    text = json.dumps(state, ensure_ascii=False)
    answers = {}
    for k, q in questions.items():
        if q["type"] == "noul":
            ins = q.get("instructions", "")
            v = next((p for key, p in NOUL.items() if key in ins), None)       # まとめて聞くときは質問の中の番号で
            if v is None:
                v = 0.1 if "候補." in ins else next((p for key, p in NOUL.items() if key in text), 0.1)
            answers[k] = dc.Answer("noul", float(v))
        elif q["type"] == "choice":
            v, p = next((c for key, c in CHOICE.items() if key in text), ("other", 0.9))
            answers[k] = dc.Answer("choice", v, {v: p}, p)
        elif q["type"] == "box":
            answers[k] = dc.Answer("box", {"top": 0.1, "bottom": 0.2, "left": 0.3, "right": 0.4}, {}, 0.9)
    return dc.DecisionResult(answers=answers, model=kw.get("model") or "typesafe/jev-1.14-20261014", latency_ms=5,
                             input_tokens=100, cost_usd=0.000004, request_id="gen-test")


@pytest.fixture(autouse=True)
def decide(monkeypatch):
    monkeypatch.setenv("DECISIONS_ENABLED", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(dc, "decide", fake_decide)
    CALLS.clear()
    NOUL.clear()
    CHOICE.clear()
    FAIL["on"] = False


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture()
def db(client):
    s = SessionLocal()
    yield s
    s.close()


# ------------------------------------------------------------------ 有効・無効
def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DECISIONS_ENABLED", raising=False)
    assert not decisions.enabled("rerank")
    monkeypatch.setenv("DECISIONS_ENABLED", "1")
    assert decisions.enabled("rerank")
    monkeypatch.setenv("DECISION_RERANK", "0")
    assert not decisions.enabled("rerank")
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert not decisions.enabled("route")


# ------------------------------------------------------------------ ① 検索の並べ替え
def test_rerank_orders_by_probability(db):
    rows = {r.defect_id: r for r in db.query(DefectReport).filter(DefectReport.defect_id.in_(
        ["KZ25-0001", "KZ25-0002", "KZ25-0072"])).all()}
    items = [{"defect_id": "KZ25-0002"}, {"defect_id": "KZ25-0001"}, {"defect_id": "KZ25-0072"}]
    NOUL["KZ25-0072"] = 0.95
    NOUL["KZ25-0001"] = 0.80
    ranked, info = decisions.rerank("ざらざら", items, rows, top_k=2, model="perplexity/pplx-decider-v1.2", mode="per_candidate")
    assert [it["defect_id"] for it in ranked] == ["KZ25-0072", "KZ25-0001"]
    assert ranked[0]["relevance"] == 0.95
    assert info["candidates"] == 3 and info["abstain"] is False
    assert all(c["model"] == "perplexity/pplx-decider-v1.2" for c in CALLS)
    # 候補1件ごとに1リクエスト、state は質問と報告書だけ
    assert len(CALLS) == 3 and set(CALLS[0]["state"]) == {"質問", "報告書"}


def test_rerank_joint_is_one_request(db):
    rows = {r.defect_id: r for r in db.query(DefectReport).filter(DefectReport.defect_id.in_(
        ["KZ25-0001", "KZ25-0002", "KZ25-0072"])).all()}
    items = [{"defect_id": "KZ25-0002"}, {"defect_id": "KZ25-0001"}, {"defect_id": "KZ25-0072"}]
    NOUL["候補.KZ25-0072"] = 0.9
    NOUL["候補.KZ25-0001"] = 0.7
    ranked, info = decisions.rerank("ざらざら", items, rows, top_k=3, mode="joint")
    assert [it["defect_id"] for it in ranked] == ["KZ25-0072", "KZ25-0001", "KZ25-0002"]
    assert len(CALLS) == 1 and set(CALLS[0]["state"]["候補"]) == {"KZ25-0001", "KZ25-0002", "KZ25-0072"}
    assert CALLS[0]["model"] == "typesafe/jev-1.14" and info["mode"] == "joint"


def test_rerank_abstains_when_nothing_fits(db):
    rows = {r.defect_id: r for r in db.query(DefectReport).limit(3)}
    ranked, info = decisions.rerank("GENOS M560-V の寸法不良", [{"defect_id": i} for i in rows], rows, top_k=3)
    assert info["abstain"] is True and info["max_relevance"] == 0.1


def test_search_uses_rerank_and_falls_back(db, monkeypatch):
    NOUL["KZ25-0040"] = 0.99
    out = rag.search(db, "主軸のクランプ圧低下", top_k=5)
    assert out[0]["defect_id"] == "KZ25-0040"
    assert out[0]["search_mode"].endswith("+rerank") and "relevance" in out[0]
    FAIL["on"] = True        # 判断モデルが失敗しても、ハイブリッド検索の順で返す
    out2 = rag.search(db, "主軸のクランプ圧低下", top_k=5)
    assert len(out2) == 5 and "relevance" not in out2[0]


def test_smart_search_api_returns_relevance(client):
    NOUL["KZ25-0040"] = 0.99
    body = client.get("/api/reports/search", params={"q": "主軸のクランプ圧低下", "top_k": 3}).json()
    assert body["search_mode"].endswith("+rerank")
    assert body["items"][0]["defect_id"] == "KZ25-0040" and body["items"][0]["relevance"] == 0.99


def test_search_without_decisions_is_unchanged(db, monkeypatch):
    monkeypatch.setenv("DECISIONS_ENABLED", "0")
    out = rag.search(db, "主軸のクランプ圧低下", top_k=5)
    assert CALLS == [] and len(out) == 5 and "relevance" not in out[0]


# ------------------------------------------------------------------ ② 質問の振り分け
def test_route_takes_only_confident_answers():
    CHOICE["何件"] = ("count", 0.92)
    r = decisions.route("主軸のクランプ圧低下が原因の報告は何件？")
    assert r["intent"] == "count" and r["taken"] is True and "検索" in r["hint"]
    CHOICE.clear()
    CHOICE["ざら"] = ("search", 0.4)
    r2 = decisions.route("ざらざらの事例")
    assert r2["taken"] is False and r2["hint"] == ""
    q = CALLS[0]["questions"]["intent"]
    assert set(q["criteria"]) == set(decisions.INTENTS) and "従わない" in q["instructions"]


def test_prompt_gets_route_hint():
    from routers import chat
    p = chat._opencode_prompt("何件？", [], "(候補)", "この質問は数を求めている。")
    assert "# 質問の種類(判断モデルの判定)" in p and "この質問は数を求めている。" in p
    assert "質問の種類" not in chat._opencode_prompt("何件？", [], "(候補)")


# ------------------------------------------------------------------ ③ 引用の確かめ
def test_check_citations(db):
    lookup = lambda did: db.query(DefectReport).filter(DefectReport.defect_id == did).first()
    NOUL["a61nx"] = 0.97
    ans = ("**結論**：[KZ25-0043] は a61nx で起きた表面キズです。\n"
           "[KZ25-0012] も同じ機械です。\nなお KZ25-9999 は存在しません。")
    res = decisions.check_citations(ans, lookup)
    by = {(c["defect_id"]): c for c in res["checks"]}
    assert by["KZ25-0043"]["supported"] is True and by["KZ25-0043"]["p"] == 0.97
    assert by["KZ25-0012"]["supported"] is False          # 報告書が文を支えない(0.1)
    assert by["KZ25-9999"]["exists"] is False and by["KZ25-9999"]["supported"] is True   # 否定の言及は正しい
    assert res["unsupported"] == 1
    # 崩れた番号(KZ2判-0039)は形で見つけて「要確認」にする
    res3 = decisions.check_citations("- 工具破損 [KZ2判-0039]\n- 表面キズ [KZ25-0043]", lookup)
    bad = [c for c in res3["checks"] if c.get("malformed")]
    assert [c["defect_id"] for c in bad] == ["KZ2判-0039"] and bad[0]["supported"] is False
    # 無い番号を「ある」と述べたら支えなし
    res2 = decisions.check_citations("[KZ25-9999] は表面キズです。", lookup)
    assert res2["checks"][0]["supported"] is False and res2["unsupported"] == 1


# ------------------------------------------------------------------ ④ 読み取りの確かめ
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def test_verify_fields_flags_mismatch_and_boxes():
    NOUL["沈用フライス"] = 0.05
    NOUL["KZ25-0050"] = 0.98
    NOUL["「中」"] = 0.9
    v = decisions.verify_fields(PNG, "image/png", {"defect_id": "KZ25-0050", "machine_name": "沈用フライス", "severity": "medium",
                                                   "customer": None})
    assert v["mismatch"] == ["machine_name"]
    assert v["checks"]["defect_id"]["ok"] is True and "box" not in v["checks"]["defect_id"]
    assert v["checks"]["machine_name"]["box"]["left"] == 0.3        # 合わない項目だけ欄の位置を聞く
    first = CALLS[0]
    assert first["state"][1]["type"] == "image_url" and first["state"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "「中」" in first["questions"]["m_severity"]["instructions"]   # 英語のコードを帳票の言葉で聞く
    assert "m_customer" not in first["questions"]                        # 空の項目は聞かない
    assert CALLS[1]["model"] == "typesafe/jev-1.14"                       # Box は Jev 1.14


def test_ingest_confidence_from_verification(client, monkeypatch):
    from services import llm
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "extract_from_document", lambda b, m, f: {
        "defect_id": "KZ25-0050", "machine_name": "沈用フライス", "customer": "藤井機器工業", "discoverer": "部司"})
    NOUL["KZ25-0050"] = 0.98
    r = client.post("/api/ingest/upload", files={"file": ("scan.png", PNG, "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] == "low"                       # 3項目が合わない → low(AI の自己申告は使わない)
    assert set(body["verification"]["mismatch"]) == {"machine_name", "customer", "discoverer"}
    assert any("使用機械" in w for w in body["warnings"])
    NOUL.update({"沈用フライス": 0.9, "藤井機器工業": 0.9, "部司": 0.9})
    body2 = client.post("/api/ingest/upload", files={"file": ("scan.png", PNG, "image/png")}).json()
    assert body2["confidence"] == "high" and body2["verification"]["mismatch"] == []
    FAIL["on"] = True                                         # 確かめに失敗しても読み取りの結果は返す(medium)
    body3 = client.post("/api/ingest/upload", files={"file": ("scan.png", PNG, "image/png")}).json()
    assert body3["confidence"] == "medium" and body3["extracted"]["defect_id"] == "KZ25-0050"
