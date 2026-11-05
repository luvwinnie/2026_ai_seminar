import csv

from database import DATA_CSV

CATEGORY_COLUMNS = {
    "customer": "customer",
    "process": "process",
    "machine": "machine_name",
    "operator": "operator_name",
    "phenomenon": "phenomenon",
    "factor": "factor",
}


def csv_nunique() -> dict[str, int]:
    """元データ（CSV）から、種類ごとの異なり数を数える。"""
    with open(DATA_CSV, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return {cat: len({r[col] for r in rows if r[col]}) for cat, col in CATEGORY_COLUMNS.items()}


def test_AC_v11_05_masters(client):
    response = client.get("/api/masters")
    assert response.status_code == 200
    body = response.json()
    assert list(body) == list(CATEGORY_COLUMNS)
    nunique = csv_nunique()
    assert nunique == {"customer": 10, "process": 8, "machine": 10, "operator": 29, "phenomenon": 12, "factor": 10}
    for category, items in body.items():
        assert sum(item["usage_count"] for item in items) == 110, category
        assert sum(1 for item in items if item["usage_count"] >= 1) == nunique[category], category
        for item in items:
            assert set(item) == {"id", "category", "name", "sort_order", "is_active", "usage_count"}
            assert item["category"] == category
        # sort_order、name の順
        assert items == sorted(items, key=lambda i: (i["sort_order"], i["name"]))


def test_AC_v11_06_initial_masters(client):
    body = client.get("/api/masters").json()
    counts = {category: len(items) for category, items in body.items()}
    assert counts == {"customer": 10, "process": 8, "machine": 10, "operator": 29, "phenomenon": 12, "factor": 10}
    assert sum(counts.values()) == 79
    assert [i["name"] for items in body.values() for i in items if i["usage_count"] == 0] == []
    assert client.get("/api/masters/unknown").status_code == 404
