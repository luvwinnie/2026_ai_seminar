"""業務質問・曖昧性・欠損・関係の多重度・実行時制約を一時DBで検証。"""
import asyncio
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# 既存テスト同様、アプリimport前に一時DBとLLM無効の環境を設定する。
import test_api  # noqa: F401
from database import Base, get_db
from fastapi.testclient import TestClient
from fastmcp import Client
import main
from models import CapaAction, DefectReport
from services import capa_service, ontology, ontology_mcp
from services.mcp_server import mcp


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        for i, machine, production, defects, cost in [(1, "Machine A", 100, 10, 100),
                (2, "Machine A", 900, 9, 200), (3, "Machine B", 0, 0, None)]:
            db.add(DefectReport(defect_id=f"OT-{i}", occurrence_date=date(2026, 1, i),
                customer="顧客A", process="切削", machine_name=machine, operator_name="作業者",
                part_number="P1", part_name="部品", production_count=production, defect_count=defects,
                defect_description="テスト", phenomenon="傷", severity="high", status="open", total_cost=cost))
        for i, report, status in [(1, "OT-1", "open"), (2, "OT-1", "in_progress"), (3, "OT-2", "closed")]:
            db.add(CapaAction(capa_id=f"CA-OT-{i}", defect_id=report, title="処置", status=status,
                              action_type="corrective", effect_note="再測定済み" if status == "closed" else None))
        db.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def db(factory):
    with factory() as db:
        yield db


@pytest.fixture
def api(factory):
    def dependency():
        with factory() as db:
            yield db
    main.app.dependency_overrides[get_db] = dependency
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.pop(get_db, None)


def test_machine_quality_question_no_capa_fanout(db):
    entity = ontology.resolve(db, "MachineLabel", "Machine A")
    assert entity["can_auto_select"]
    oid = entity["candidates"][0]["object_id"]
    result = ontology.query_quality(db, ontology.QualityQuery(scope={"machine_id": oid}, limit=1))
    m = result["metrics"]
    assert m["report_count"] == 2  # 2つのCAPAがあるOT-1を二重計上しない
    assert Decimal(m["known_loss_jpy"]) == 300
    assert m["recorded_defect_rate"] == pytest.approx(19 / 1000)  # 率の単純平均ではない
    assert m["open_capa_count"] == 2
    assert result["total"] == 2 and len(result["objects"]) == 1 and result["next_offset"] == 1
    assert result["provenance"]["query"]["scope"]["machine_id"] == oid
    assert result["objects"][0]["source"]["citation"].startswith("[OT-")


def test_scope_uses_exists_and_inclusive_occurrence_dates(db):
    r = ontology.query_quality(db, ontology.QualityQuery(scope={"has_open_capa": True}))
    assert r["metrics"]["report_count"] == 1
    assert Decimal(r["metrics"]["known_loss_jpy"]) == 100
    r = ontology.query_quality(db, ontology.QualityQuery(scope={"date_from": "2026-01-02", "date_to": "2026-01-02"}))
    assert [o["object_id"] for o in r["objects"]] == ["OT-2"]


def test_missing_cost_zero_denominator_and_invalid_quantities(db):
    r = ontology.query_quality(db, ontology.QualityQuery(scope={"defect_id": "OT-3"}))
    assert r["metrics"]["known_loss_jpy"] is None
    assert r["metrics"]["missing_loss_reports"] == 1
    assert r["metrics"]["recorded_defect_rate"] is None
    assert len(r["quality"]) == 2
    db.query(DefectReport).filter_by(defect_id="OT-1").update({"defect_count": 101})
    r = ontology.query_quality(db, ontology.QualityQuery())
    assert r["metrics"]["recorded_defect_rate"] is None
    assert r["metrics"]["invalid_quantity_reports"] == 1


def test_empty_scope_result_is_not_missing_data(db):
    r = ontology.query_quality(db, ontology.QualityQuery(scope={"date_from": "2030-01-01"}))
    assert r["metrics"]["report_count"] == 0
    assert r["metrics"]["known_loss_jpy"] == "0"
    assert r["metrics"]["recorded_defect_rate"] is None


def test_entity_candidates_and_unknown_name_not_auto_substituted(db):
    r = ontology.resolve(db, "MachineLabel", "Machine")
    assert r["total"] == 2 and not r["can_auto_select"]
    r = ontology.resolve(db, "MachineLabel", "Machine B")
    assert r["can_auto_select"]
    r = ontology.resolve(db, "MachineLabel", "B")  # 候補が1つでも部分一致なら確認
    assert r["total"] == 1 and not r["can_auto_select"]
    assert ontology.resolve(db, "MachineLabel", "架空9000")["candidates"] == []
    assert ontology.resolve(db, "MachineLabel", "machine a")["match"] == "normalized"
    assert ontology.resolve(db, "MachineLabel", "' OR 1=1 --")["candidates"] == []


def test_normalization_collision_requires_confirmation(db):
    db.query(DefectReport).filter_by(defect_id="OT-3").update({"machine_name": "Ｍａｃｈｉｎｅ Ａ"})
    r = ontology.resolve(db, "MachineLabel", "machine a")
    assert r["total"] == 2 and not r["can_auto_select"]


def test_typed_links_both_directions_and_orphan(db):
    machine = ontology.traverse(db, "DefectReport", "OT-1", "recorded_on")["objects"][0]
    reports = ontology.traverse(db, "MachineLabel", machine["object_id"], "reports")
    assert reports["total"] == 2
    cap = ontology.traverse(db, "DefectReport", "OT-1", "has_capa", 1)
    assert cap["total"] == 2 and cap["next_offset"] == 1
    report = ontology.traverse(db, "CapaAction", cap["objects"][0]["object_id"], "for_report")
    assert report["objects"][0]["object_id"] == "OT-1"
    with pytest.raises(ontology.OntologyError):
        ontology.traverse(db, "MachineLabel", machine["object_id"], "has_capa")
    db.query(CapaAction).filter_by(capa_id="CA-OT-1").update({"defect_id": "deleted"})
    orphan = ontology.traverse(db, "CapaAction", "CA-OT-1", "for_report")
    assert orphan["total"] == 0 and orphan["quality"]


@pytest.mark.parametrize("payload", [
    {"scope": {"machine_id": "MachineLabel:made-up"}},
    {"scope": {"machine_id": ontology.label_id("Customer", "顧客A")}},
    {"scope": {"machine_id": ontology.label_id("MachineLabel", "存在しない機械")}},
    {"scope": {"date_from": "2026-02-30"}}, {"scope": {"date_from": "2027-01-01", "date_to": "2026-01-01"}},
    {"scope": {"machine_name": "Machine A"}}, {"scope": {"status": "closed"}},
    {"scope": {"has_open_capa": "false"}}, {"scope": {"defect_id": "unknown"}},
    {"limit": 0}, {"offset": -1}, {"group_by": "arbitrary_sql"}, {"sql": "DROP TABLE defect_reports"},
])
def test_invalid_queries_do_not_silently_broaden_scope(api, payload):
    assert api.post("/api/ontology/query", json=payload).status_code == 422


def test_rest_preview_and_execution_share_closed_state_constraint(api, db):
    for note in ("", "   "):
        r = api.post("/api/ontology/actions/capa/preview", json={"capa_id": "CA-OT-1", "status": "closed", "effect_note": note})
        assert r.status_code == 200 and r.json()["valid"] is False and r.json()["saved"] is False
        assert api.put("/api/capa/CA-OT-1", json={"status": "closed", "effect_note": note}).status_code == 409
    preview = api.post("/api/ontology/actions/capa/preview", json={"capa_id": "CA-OT-1", "status": "closed", "effect_note": "検査で確認"}).json()
    assert preview["valid"] and not preview["saved"] and preview["after"]["status"] == "closed"
    db.expire_all()
    assert db.query(CapaAction).filter_by(capa_id="CA-OT-1").one().status == "open"
    assert api.put("/api/capa/CA-OT-1", json={"status": "closed", "effect_note": "検査で確認"}).status_code == 200
    # statusを省略して効果確認メモだけ消す経路も拒否。
    assert api.put("/api/capa/CA-OT-1", json={"effect_note": "  "}).status_code == 409
    assert api.put("/api/capa/CA-OT-1", json={"action_type": "invented"}).status_code == 409
    assert api.put("/api/capa/CA-OT-1", json={"due_date": "invalid"}).status_code == 409


def test_preview_does_not_bypass_execution_revalidation(db):
    assert capa_service.preview_update(db, "CA-OT-3", {"owner": "担当者"})["valid"]
    db.query(DefectReport).filter_by(defect_id="OT-2").delete()
    with pytest.raises(capa_service.CapaError, match="報告書"):
        capa_service.update(db, "CA-OT-3", {"owner": "担当者"})


def test_mcp_discovery_resource_and_tool_roundtrip(factory, monkeypatch):
    monkeypatch.setattr(ontology_mcp, "SessionLocal", factory)
    async def run():
        async with Client(mcp) as client:
            tools = {t.name: t for t in await client.list_tools()}
            assert tools["query_quality_ontology"].annotations.readOnlyHint
            assert "scope" in tools["query_quality_ontology"].inputSchema["properties"]
            resources = await client.list_resources()
            assert any(str(r.uri) == "ontology://quality/definition" for r in resources)
            content = await client.read_resource("ontology://quality/definition")
            assert '"recorded_defect_rate"' in content[0].text
            result = await client.call_tool("query_quality_ontology", {"scope": {"has_open_capa": True}})
            assert result.data["metrics"]["report_count"] == 1
            bad = await client.call_tool("query_quality_ontology", {"scope": {"machine_id": "wrong"}}, raise_on_error=False)
            assert bad.is_error
    asyncio.run(run())


def test_both_chat_paths_supply_ontology_context(api, factory, monkeypatch):
    from routers import chat
    captured = []
    monkeypatch.setattr(chat, "SessionLocal", factory)
    monkeypatch.setattr(chat, "_build_context", lambda *_: ("候補なし", []))
    monkeypatch.setattr(chat, "chat_backend", lambda: "opencode")
    def ask(system, prompt):
        captured.append(system)
        return "回答"
    def stream(system, prompt):
        captured.append(system)
        yield {"type": "token", "text": "回答"}
    monkeypatch.setattr(chat.opencode_client, "ask", ask)
    monkeypatch.setattr(chat.opencode_client, "stream", stream)
    assert api.post("/api/chat", json={"message": "Machine Aの損失は？"}).status_code == 200
    assert api.post("/api/chat/stream", json={"message": "Machine Aの損失は？"}).status_code == 200
    assert len(captured) == 2
    for system in captured:
        assert "SUM(defect_count) / SUM(production_count)" in system
        assert "query_quality_ontology" in system and "can_auto_select=false" in system
        assert "工場全体" in system and "preview_capa_update" in system


def test_graph_uses_defined_relations_and_real_keys(api):
    graph = api.get('/api/ontology/graph/OT-1').json()
    assert len(graph['nodes']) == 6  # 報告・機械・工程・顧客・CAPA2件
    assert len(graph['edges']) == 5
    nodes = {n['id']: n for n in graph['nodes']}
    assert nodes[graph['root']]['object_id'] == 'OT-1'
    for edge in graph['edges']:
        assert edge['source'] == graph['root']
        assert edge['target'] in nodes
        assert edge['evidence']['report_id'] == 'OT-1'
    assert graph['relation_counts']['has_capa'] == 2
    assert not graph['truncated_relations']
    capped = api.get('/api/ontology/graph/OT-1?capa_limit=1').json()
    assert len(capped['nodes']) == 5 and capped['truncated_relations'][0]['total'] == 2
    empty = api.get('/api/ontology/graph/OT-3').json()
    assert len(empty['nodes']) == 4 and empty['relation_counts']['has_capa'] == 0
    assert all(n['object_type'] != 'CapaAction' for n in empty['nodes'])
    assert api.get('/api/ontology/graph/missing').status_code == 422

