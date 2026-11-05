from fastapi.testclient import TestClient

from main import app


def test_AC_v10_01_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "reports": 110, "chat_backend": "none"}


def test_AC_v10_01_restart_does_not_duplicate(client):
    # もう一度起動しても、同じ報告書・マスタを二重に入れない
    with TestClient(app) as again:
        assert again.get("/health").json()["reports"] == 110
        masters = again.get("/api/masters").json()
        assert sum(len(items) for items in masters.values()) == 79
