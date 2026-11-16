from fastapi.testclient import TestClient
from app.main import app


def test_health():
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_only_private_api_routes_are_exposed():
    paths = set(TestClient(app).get('/openapi.json').json()['paths'])
    assert paths == {'/api/v1/health', '/api/v1/tasks/{task_id}',
                     '/api/v1/analyses/policy', '/api/v1/analyses', '/api/v1/analyses/{analysis_id}'}
