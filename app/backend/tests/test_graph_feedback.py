# -*- coding: utf-8 -*-
"""関連マップ(/api/graph)とチャットフィードバック(/api/chat/feedback)のテスト。"""
import os
import sys
import tempfile
from pathlib import Path

_tmpdir = tempfile.mkdtemp(prefix="defect_graph_test_")
os.environ.setdefault("DB_PATH", str(Path(_tmpdir) / "test.db"))
os.environ.setdefault("EMBEDDINGS", "off")
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from database import SessionLocal  # noqa: E402


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


def test_graph_endpoint(client):
    r = client.get("/api/graph")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] in ("embedding", "jaccard")
    assert len(body["nodes"]) > 0
    ids = {n["id"] for n in body["nodes"]}
    for l_ in body["links"]:
        assert l_["s"] in ids and l_["t"] in ids
        assert 0 < l_["w"] <= 1.0001


def test_graph_expand_scores(client, db):
    from services import graph as graph_service

    g = graph_service.get_graph(db)
    # 相互縁を持つ節を1つ選び、その近傍が伝播で浮上することを確認
    src = next((i for i, adj in g["adj"].items() if any(m for _, _, m in adj)), None)
    if src is None:
        return  # 縁が無いデータでは中立(スキップ相当)
    out = graph_service.expand_scores(db, {src: 1.0})
    assert out[src] == 1.0
    neigh = [j for j, _, m in g["adj"][src] if m]
    assert any(out.get(j, 0) > 0 for j in neigh)


def test_feedback_roundtrip(client):
    r = client.post("/api/chat/feedback", json={
        "session_id": 1, "message_index": 1, "rating": -1,
        "comment": "引用と内容が一致しない", "answer_excerpt": "テスト回答",
    })
    assert r.status_code == 201
    r2 = client.get("/api/chat/feedback")
    assert r2.status_code == 200
    body = r2.json()
    assert body["down"] >= 1
    assert body["items"][0]["comment"] == "引用と内容が一致しない"


def test_feedback_invalid_rating(client):
    r = client.post("/api/chat/feedback", json={"rating": 5})
    assert r.status_code == 422
