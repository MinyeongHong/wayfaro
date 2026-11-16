from fastapi.testclient import TestClient
from app.main import app


def test_health():
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_invalid_job_input():
    response = TestClient(app).post("/api/v1/jobs", json={"raw_text": "short"})
    assert response.status_code == 422
