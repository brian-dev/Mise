from fastapi.testclient import TestClient

from mise_ai.main import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
