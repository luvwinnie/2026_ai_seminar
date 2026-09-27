"""報告書トリアージ(判断モデル Jev + LangGraph)のテスト。

Jev は呼ばない(decision_client.decide を差し替える)。ネットワーク・費用なしで、
閾値の採否、LLM へ回る条件、CAPA への分岐、人の承認で止まって再開する流れ、API を確かめる。
"""
import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_DIR.parents[1]
sys.path.insert(0, str(BACKEND_DIR))

_tmpdir = tempfile.mkdtemp(prefix="defectreport_triage_")
os.environ.setdefault("DB_PATH", str(Path(_tmpdir) / "test.db"))
os.environ.setdefault("DATA_CSV", str(APP_ROOT / "data" / "defect_reports.csv"))
os.environ.setdefault("CHROMA_PATH", str(Path(_tmpdir) / "chroma"))
os.environ.setdefault("EMBEDDINGS", "off")
os.environ.pop("OPENCODE_URL", None)
os.environ["TRIAGE_CHECKPOINT_DB"] = str(Path(_tmpdir) / "triage_checkpoints.db")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import CapaAction, DefectReport  # noqa: E402
from services import decision_client as dc  # noqa: E402
from services import triage, triage_graph  # noqa: E402

# 判断モデルの答え(テストごとに書き換える)
SCRIPT: dict = {}


def _answer(key: str, q: dict) -> dc.Answer:
    spec = SCRIPT.get(key)
    if q["type"] == "choice":
        options = list(q["criteria"])
        value, conf = spec if spec else (options[0], 0.95)
        return dc.Answer("choice", value, {value: conf}, conf)
    if q["type"] == "score":
        level, conf = spec if spec else (1, 0.6)
        return dc.Answer("score", float(level), {str(level): conf}, conf)
    return dc.Answer("noul", float(spec if spec is not None else 0.1))


def fake_decide(state, questions, retries=3, **kw):
    return dc.DecisionResult(answers={k: _answer(k, q) for k, q in questions.items()},
                             model="typesafe/jev-1.13-20260917", latency_ms=5, input_tokens=100, cost_usd=0.000004,
                             request_id="gen-test")


@pytest.fixture(autouse=True)
def jev(monkeypatch):
    monkeypatch.setenv("JEV_ENABLED", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(dc, "decide", fake_decide)
    SCRIPT.clear()
    yield


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def _report(client, *, without_capa=True) -> DefectReport:
    """登録値のそろった報告書を1件選ぶ(CAPA がまだ無いもの)。"""
    with SessionLocal() as db:
        taken = {d for (d,) in db.query(CapaAction.defect_id).distinct()}
        for r in db.query(DefectReport).order_by(DefectReport.id.desc()):
            if r.factor in triage.FACTOR_TO_4M and r.cause and (not without_capa or r.defect_id not in taken):
                return r
    raise AssertionError("条件に合う報告書がありません")


def _confident(r: DefectReport):
    SCRIPT.update({"phenomenon": (r.phenomenon, 0.97), "factor": (r.factor, 0.96),
                   "category_4m": (triage.FACTOR_TO_4M[r.factor], 0.9)})


# ------------------------------------------------------------------ 閾値の採否(コード)
def test_interpret_accepts_only_above_threshold():
    th = dict(triage.DEFAULT_THRESHOLDS, phenomenon=0.7, factor=0.5)
    answers = {
        "phenomenon": dc.Answer("choice", "表面キズ", {}, 0.65),
        "factor": dc.Answer("choice", "設備不調", {}, 0.9),
        "category_4m": dc.Answer("choice", "Man", {}, 0.7),       # 対応表では Machine → 食い違い
        "severity": dc.Answer("score", 2.0, {"2": 0.95}, 0.95),
        "systemic": dc.Answer("noul", 0.55),                      # 五分五分に近い → 採らない
        "outflow": dc.Answer("noul", 0.05),                       # はっきり偽 → 採る
    }
    d = triage.interpret(answers, th)
    assert d["phenomenon"]["accepted"] is False
    assert d["factor"]["accepted"] is True
    assert d["category_4m"]["value"] == "Machine" and d["category_4m"]["source"] == "rule"
    # 要因が採用なら 4M も採用。Jev の答え(Man)は照合用に残り、食い違いが分かる
    assert d["category_4m"]["accepted"] is True and d["category_4m"]["rule_agrees_with_jev"] is False
    assert d["category_4m"]["jev_value"] == "Man" and d["category_4m"]["confidence"] == 0.9
    assert d["severity"]["value"] == "high"
    assert d["systemic"]["accepted"] is False
    assert d["outflow"]["accepted"] is True and d["outflow"]["value"] is False


def test_interpret_other_is_never_accepted():
    d = triage.interpret({"phenomenon": dc.Answer("choice", triage.OTHER, {}, 0.99)})
    assert d["phenomenon"]["value"] is None and d["phenomenon"]["accepted"] is False


# ------------------------------------------------------------------ グラフの分岐
def test_confident_report_skips_llm_and_capa(client):
    r = _report(client)
    _confident(r)
    out = triage_graph.run(r.defect_id)
    assert out["status"] == "completed"
    assert out["route"] == ["prepare", "judge", "merge", "plan"]
    assert out["llm"] is None and out["escalation"]["needed"] is False
    assert out["conflicts"] == []
    assert out["jev"]["calls"] == 2  # 不具合内容と原因を別々に聞く


def test_low_confidence_goes_to_llm_review(client):
    r = _report(client)
    _confident(r)
    SCRIPT["phenomenon"] = (r.phenomenon, 0.2)
    out = triage_graph.run(r.defect_id)
    assert "llm_review" in out["route"]
    assert out["llm"]["fields"] == ["phenomenon"]
    assert out["llm"]["backend"] is None          # LLM 未設定 → 人が確かめる提案のまま
    assert out["decisions"]["phenomenon"]["accepted"] is False


def test_conflict_with_registered_value_is_reported(client):
    r = _report(client)
    _confident(r)
    other = next(p for p in triage.PHENOMENON_HINTS if p != r.phenomenon)
    SCRIPT["phenomenon"] = (other, 0.98)
    out = triage_graph.run(r.defect_id)
    assert {"field": "phenomenon", "registered": r.phenomenon, "suggested": other,
            "confidence": 0.98} in out["conflicts"]


def test_outflow_escalates_to_capa_and_waits_for_approval_then_applies(client):
    r = _report(client)
    _confident(r)
    SCRIPT["outflow"] = 0.95
    out = triage_graph.run(r.defect_id)
    assert out["status"] == "waiting_approval"
    assert out["route"][-1] == "draft_capa"  # human_review の中で止まっている(まだ完了していない)
    actions = out["capa_draft"]["actions"]
    assert actions, "類似事例の対策から処置案ができる"
    assert all("jev_fits_cause" in a for a in actions)  # LLM/類似事例の案を Jev が確かめた

    done = triage_graph.resume(out["run_id"], approved=True, selected=[0], note="ok")
    assert done["status"] == "approved"
    assert len(done["created_capa"]) == 1
    with SessionLocal() as db:
        assert db.query(CapaAction).filter_by(capa_id=done["created_capa"][0]).count() == 1

    with pytest.raises(ValueError):
        triage_graph.resume(out["run_id"], approved=True, selected=[0])  # 二度は進めない


def test_rejected_review_creates_nothing(client):
    r = _report(client)
    _confident(r)
    SCRIPT["outflow"] = 0.95
    out = triage_graph.run(r.defect_id)
    with SessionLocal() as db:
        before = db.query(CapaAction).count()
    done = triage_graph.resume(out["run_id"], approved=False, selected=[])
    assert done["status"] == "rejected" and not done.get("created_capa")
    with SessionLocal() as db:
        assert db.query(CapaAction).count() == before


# ------------------------------------------------------------------ API
def test_api_status_preview_run_latest(client):
    s = client.get("/api/triage/status").json()
    assert s["enabled"] is True and s["backend"] == "openrouter"
    assert set(triage.DEFAULT_THRESHOLDS) <= set(s["thresholds"])

    p = client.post("/api/triage/preview", json={"defect_description": "外周に線状のキズ", "cause": ""})
    assert p.status_code == 200
    assert p.json()["decisions"]["info_missing"]["source"] == "rule"  # 原因が空 → コードで判定

    r = _report(client)
    _confident(r)
    run = client.post(f"/api/triage/reports/{r.defect_id}")
    assert run.status_code == 200 and run.json()["status"] == "completed"
    latest = client.get(f"/api/triage/reports/{r.defect_id}").json()
    assert latest["run_id"] == run.json()["run_id"]
    assert client.post(f"/api/triage/runs/{latest['run_id']}/resume", json={"approved": True}).status_code == 409
    assert client.post("/api/triage/reports/KZ99-9999").status_code == 404


def test_api_is_503_when_disabled(client, monkeypatch):
    monkeypatch.setenv("JEV_ENABLED", "0")
    assert client.get("/api/triage/status").json()["enabled"] is False
    assert client.post("/api/triage/preview", json={"defect_description": "x"}).status_code == 503


# ------------------------------------------------------------------ クライアント(HTTP)
def test_decision_client_retries_on_overload(monkeypatch):
    monkeypatch.undo()  # 本物の decide を使う
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    dc.clear_cache()
    calls = []

    def post(self, url, json=None, headers=None):
        calls.append(url)
        req = httpx.Request("POST", url)
        if len(calls) == 1:
            return httpx.Response(529, text="overloaded", request=req)
        return httpx.Response(200, request=req, json={
            "model": "typesafe/jev-1.13", "id": "gen-1", "usage": {"input_tokens": 10, "cost": 1e-6},
            "answers": {"q": {"type": "choice", "choice": "a", "probabilities": {"a": 0.9, "b": 0.1},
                              "confidence": 0.8}}})

    monkeypatch.setattr(httpx.Client, "post", post)
    res = dc.decide("s", {"q": dc.choice("?", {"a": None, "b": None})})
    assert len(calls) == 2 and calls[0].endswith("/api/alpha/decisions")
    assert res.answers["q"].value == "a" and res.answers["q"].confidence == 0.8
    assert res.request_id == "gen-1"


def test_decision_client_raises_without_retry_on_422(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    dc.clear_cache()
    calls = []

    def post(self, url, json=None, headers=None):
        calls.append(1)
        return httpx.Response(422, text="bad question", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", post)
    with pytest.raises(dc.DecisionError):
        dc.decide("s", {"q": dc.noul("?", "yes", "no")})
    assert len(calls) == 1



# ------------------------------------------------------------------ 2026-09-27 の改善(公式の勧めと実践の報告から)
def test_margin_is_required_not_only_top_probability():
    th = dict(triage.DEFAULT_THRESHOLDS, phenomenon=0.7)
    mg = dict(triage.DEFAULT_MARGINS, phenomenon=0.3)
    close = {"phenomenon": dc.Answer("choice", "表面キズ", {"表面キズ": 0.72, "角部欠け": 0.26, "その他": 0.02}, 0.58)}
    clear = {"phenomenon": dc.Answer("choice", "表面キズ", {"表面キズ": 0.72, "角部欠け": 0.08, "その他": 0.2}, 0.58)}
    a = triage.interpret(close, th, mg)["phenomenon"]
    b = triage.interpret(clear, th, mg)["phenomenon"]
    assert a["p_top"] == 0.72 and a["margin"] == 0.46 and a["accepted"] is True
    tight = {"phenomenon": dc.Answer("choice", "表面キズ", {"表面キズ": 0.72, "角部欠け": 0.27}, 0.44)}
    c = triage.interpret(tight, th, dict(mg, phenomenon=0.5))["phenomenon"]
    assert c["margin"] == 0.45 and c["accepted"] is False   # 1位は高いが、2位と近い
    assert b["accepted"] is True


def test_model_family_and_mismatch_blocks_auto_accept(client, monkeypatch):
    assert dc.model_family("typesafe/jev-1.13-20260917") == dc.model_family("jev-1.13.0") == "jev-1.13"
    assert dc.model_family("~typesafe/jev-latest") == "jev-latest"
    r = _report(client)
    _confident(r)
    monkeypatch.setattr(triage, "measured_model", lambda: "typesafe/jev-9.9-20270101")
    out = triage_graph.run(r.defect_id)
    assert out["jev"]["model_matches_thresholds"] is False
    assert not any(out["decisions"][k]["accepted"] for k in ("phenomenon", "factor", "category_4m"))
    assert any("版" in n for n in out["jev"]["notes"])


def test_info_missing_blocks_auto_accept_of_phenomenon(client):
    r = _report(client)
    _confident(r)
    SCRIPT["info_missing"] = 0.9
    out = triage_graph.run(r.defect_id)
    assert out["decisions"]["info_missing"]["accepted"] is True
    assert out["decisions"]["phenomenon"]["accepted"] is False
    assert out["jev"]["criteria_hash"] and out["jev"]["notes"]


def test_capa_actions_are_checked_with_three_literal_questions(client):
    r = _report(client)
    _confident(r)
    SCRIPT.update({"outflow": 0.95, "cause": 0.9, "recurrence": 0.4, "concrete": 0.8})
    out = triage_graph.run(r.defect_id)
    a = out["capa_draft"]["actions"][0]
    assert set(a["jev_checks"]) == {"cause", "recurrence", "concrete"}
    assert a["jev_fits_cause"] == 0.9 and a["jev_ok"] is False     # 1問でも届かなければ人が選ぶ
    triage_graph.resume(out["run_id"], approved=False, selected=[])


def test_metrics_compare_latest_run_with_registered_values(client):
    r = _report(client)
    _confident(r)
    triage_graph.run(r.defect_id)
    m = client.get("/api/triage/metrics").json()
    assert m["reports"] >= 1 and m["measured_model"]
    ph = m["fields"]["phenomenon"]
    assert ph["judged"] >= 1 and 0 <= ph["auto_rate"] <= 1
    s = client.get("/api/triage/status").json()
    assert s["zdr"] is True and "phenomenon" in s["margins"]


def test_client_sends_zdr_session_pinned_model_and_caches(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("DECISION_MODEL", raising=False)
    dc.clear_cache()
    bodies = []

    def post(self, url, json=None, headers=None):
        bodies.append(json)
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "model": "typesafe/jev-1.13-20260917", "id": "gen-2", "usage": {"input_tokens": 10, "cost": 1e-6},
            "answers": {"q": {"type": "noul", "noul": 0.9}}})

    monkeypatch.setattr(httpx.Client, "post", post)
    q = {"q": dc.noul("?", "yes", "no")}
    first = dc.decide({"原因": "x"}, q, session_id="tr-1")
    again = dc.decide({"原因": "x"}, q, session_id="tr-1")
    assert len(bodies) == 1 and again.cached and not first.cached       # 同じ入力は使い回す
    b = bodies[0]
    assert b["model"] == dc.PINNED["openrouter"]                        # 版を固定
    assert b["provider"] == {"zdr": True, "data_collection": "deny"}    # データを残さない経路
    assert b["session_id"] == "tr-1"
    dc.decide({"原因": "x"}, q, use_cache=False)
    assert len(bodies) == 2


def test_client_honors_retry_after(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    dc.clear_cache()
    slept, calls = [], []
    monkeypatch.setattr(dc.time, "sleep", lambda s: slept.append(s))

    def post(self, url, json=None, headers=None):
        calls.append(1)
        req = httpx.Request("POST", url)
        if len(calls) == 1:
            return httpx.Response(429, text="slow down", headers={"retry-after": "2"}, request=req)
        return httpx.Response(200, request=req, json={"model": "typesafe/jev-1.13-20260917", "usage": {},
                                                      "answers": {"q": {"type": "noul", "noul": 0.1}}})

    monkeypatch.setattr(httpx.Client, "post", post)
    dc.decide("s2", {"q": dc.noul("?", "yes", "no")})
    assert slept == [2.0] and len(calls) == 2
