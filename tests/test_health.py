from __future__ import annotations


def test_health(client) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["service"] == "poker-table"
    assert payload["data"]["status"] == "up"

