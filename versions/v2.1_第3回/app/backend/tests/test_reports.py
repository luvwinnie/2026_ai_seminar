import pytest

from conftest import ids

KZ25_0043 = {
    "defect_id": "KZ25-0043",
    "occurrence_date": "2025-09-13",
    "report_date": "2025-09-24",
    "customer": "翠峰重工業",
    "discoverer": "祢津",
    "process": "マシニング",
    "machine_name": "a61nx",
    "operator_name": "荻原",
    "part_number": "KRS-A58-5211-D",
    "part_name": "補機マウントリブ",
    "production_count": 12,
    "defect_count": 3,
    "defect_rate": 0.25,
    "phenomenon": "表面キズ",
    "factor": "習熟不足",
    "category_4m": "Man",
    "severity": "medium",
    "status": "completed",
    "material_cost": 20179,
    "processing_cost": 40402,
    "outsourcing_cost": 0,
    "other_cost": 0,
    "total_cost": 60581,
    "is_recurrence": False,
    "has_procedure": True,
}


def test_AC_v10_02_default_order(client):
    response = client.get("/api/reports", params={"limit": 500})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 110
    assert len(body["items"]) == 110
    assert body["items"][0]["defect_id"] == "KZ25-0110"
    assert body["items"][0]["occurrence_date"] == "2026-03-15"
    assert body["items"][-1]["defect_id"] == "KZ25-0001"
    assert body["items"][-1]["occurrence_date"] == "2025-04-07"


def test_AC_v10_02_default_limit_is_50(client):
    body = client.get("/api/reports").json()
    assert body["total"] == 110
    assert len(body["items"]) == 50


def test_AC_v10_03_machine_a61nx(client):
    response = client.get("/api/reports", params={"machine": "a61nx"})
    assert ids(response) == ["KZ25-0056", "KZ25-0043", "KZ25-0019"]


def test_AC_v10_04_september(client):
    response = client.get("/api/reports", params={"date_from": "2025-09-01", "date_to": "2025-09-30"})
    assert response.json()["total"] == 7
    assert sorted(ids(response)) == [f"KZ25-00{n}" for n in range(42, 49)]


def test_AC_v10_05_machine_and_september(client):
    response = client.get(
        "/api/reports", params={"machine": "a61nx", "date_from": "2025-09-01", "date_to": "2025-09-30"}
    )
    assert response.json()["total"] == 1
    assert ids(response) == ["KZ25-0043"]


def test_AC_v10_06_zero_is_not_error(client):
    response = client.get(
        "/api/reports", params={"machine": "a61nx", "date_from": "2025-10-01", "date_to": "2025-10-31"}
    )
    assert response.status_code == 200
    assert response.json() == {"total": 0, "items": []}


def test_AC_v10_07_detail(client):
    response = client.get("/api/reports/KZ25-0043")
    assert response.status_code == 200
    body = response.json()
    for key, expected in KZ25_0043.items():
        assert body[key] == expected, key
    costs = ["material_cost", "processing_cost", "outsourcing_cost", "other_cost"]
    assert sum(body[c] for c in costs) == body["total_cost"]


def test_AC_v10_08_not_found(client):
    response = client.get("/api/reports/KZ25-9999")
    assert response.status_code == 404
    assert response.json() == {"detail": "報告書が見つかりません"}


def test_AC_v10_09_sort(client):
    assert ids(client.get("/api/reports", params={"sort": "occurrence_date", "limit": 1})) == ["KZ25-0001"]
    top3 = client.get("/api/reports", params={"sort": "-total_cost", "limit": 3}).json()["items"]
    assert [(r["defect_id"], r["total_cost"]) for r in top3] == [
        ("KZ25-0042", 13352206),
        ("KZ25-0030", 6031263),
        ("KZ25-0057", 4705954),
    ]


def test_AC_v10_09_sort_rules(client):
    # 同じ発生日は defect_id で同じ向き（既定の並びで 0109 → 0108）
    assert ids(client.get("/api/reports", params={"limit": 3})) == ["KZ25-0110", "KZ25-0109", "KZ25-0108"]
    # 知らない名前は occurrence_date として扱い、- の向きは残す
    assert ids(client.get("/api/reports", params={"sort": "-unknown", "limit": 1})) == ["KZ25-0110"]
    assert ids(client.get("/api/reports", params={"sort": "unknown", "limit": 1})) == ["KZ25-0001"]
    # severity は重さの順
    items = client.get("/api/reports", params={"sort": "-severity", "limit": 500}).json()["items"]
    order = [r["severity"] for r in items]
    assert order == ["critical"] * 7 + ["high"] * 43 + ["medium"] * 30 + ["low"] * 30
    # 不良数が多い順
    items = client.get("/api/reports", params={"sort": "-defect_count", "limit": 500}).json()["items"]
    counts = [r["defect_count"] for r in items]
    assert counts == sorted(counts, reverse=True)


def test_AC_v10_10_paging(client):
    body = client.get("/api/reports", params={"limit": 25, "offset": 100}).json()
    assert body["total"] == 110
    assert len(body["items"]) == 10


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
def test_AC_v10_10_paging_out_of_range(client, params):
    assert client.get("/api/reports", params=params).status_code == 422


@pytest.mark.parametrize("q, total", [("KZ25-004", 10), ("補機マウントリブ", 5), ("a61nx", 0)])
def test_AC_v10_11_keyword(client, q, total):
    response = client.get("/api/reports", params={"q": q})
    assert response.status_code == 200
    assert response.json()["total"] == total


def test_AC_v10_11_keyword_ids(client):
    response = client.get("/api/reports", params={"q": "KZ25-004", "sort": "defect_id"})
    assert ids(response) == [f"KZ25-004{n}" for n in range(10)]


def test_AC_v10_12_filters(client):
    response = client.get("/api/reports", params={"status": "open", "sort": "defect_id"})
    assert ids(response) == ["KZ25-0001", "KZ25-0005", "KZ25-0051", "KZ25-0090"]
    assert client.get("/api/reports", params={"severity": "high"}).json()["total"] == 43
    assert client.get("/api/reports", params={"process": "マシニング"}).json()["total"] == 7
    assert client.get("/api/reports", params={"category_4m": "Man"}).json()["total"] == 50


def test_AC_v11_01_invalid_date(client):
    response = client.get("/api/reports", params={"date_from": "2025-13-01"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"] == ["query", "date_from"]
    assert detail[0]["msg"]


def test_AC_v11_02_reversed_period(client):
    response = client.get("/api/reports", params={"date_from": "2025-10-01", "date_to": "2025-09-01"})
    assert response.status_code == 422
    assert response.json() == {
        "detail": [{
            "type": "date_range",
            "loc": ["query", "date_from"],
            "msg": "date_from is after date_to",
            "input": "2025-10-01",
        }]
    }


def test_AC_v11_03_inclusive(client):
    response = client.get("/api/reports", params={"date_from": "2025-09-08", "date_to": "2025-09-21"})
    assert response.json()["total"] == 7
    assert {"KZ25-0042", "KZ25-0047", "KZ25-0048"} <= set(ids(response))
    response = client.get("/api/reports", params={"date_from": "2025-09-17", "date_to": "2025-09-17"})
    assert sorted(ids(response)) == ["KZ25-0045", "KZ25-0046"]


def test_AC_v10_12_filters_customer_operator_phenomenon(client):
    # 04_API設計書.md §4.1 の客先・作業者・現象の完全一致（MCP の list_defect_reports と同じ処理）
    assert client.get("/api/reports", params={"customer": "翠峰重工業"}).json()["total"] == 32
    assert client.get("/api/reports", params={"operator": "荻原"}).json()["total"] == 6
    assert client.get("/api/reports", params={"phenomenon": "表面キズ"}).json()["total"] == 38
