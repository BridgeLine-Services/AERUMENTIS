"""Aerumentis — Integration Tests: API endpoints."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from aerumentis.main import app
    with TestClient(app) as c:
        yield c


class TestRootAndHealth:
    def test_root_endpoint(self, client):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Aerumentis"
        assert data["version"] == "0.1.0"

    def test_health_endpoint(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("healthy", "degraded")
        assert "services" in data

    def test_health_endpoint_trailing_slash(self, client):
        assert client.get("/api/v1/health/").status_code == 200


class TestAuthentication:
    def test_protected_endpoint_without_token(self, client):
        assert client.post("/api/v1/chat/query", json={"question": "test question"}).status_code == 401

    def test_protected_endpoint_with_invalid_token(self, client):
        r = client.post("/api/v1/chat/query", json={"question": "test question"},
                        headers={"Authorization": "Bearer invalid.token.here"})
        assert r.status_code == 401

    def test_documents_stats_without_auth(self, client):
        assert client.get("/api/v1/documents/stats").status_code == 401


class TestAPIDocumentation:
    def test_openapi_schema(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        assert r.json()["info"]["title"] == "Aerumentis"

    def test_swagger_docs(self, client):
        assert client.get("/docs").status_code == 200

    def test_redoc(self, client):
        assert client.get("/redoc").status_code == 200


class TestModuleStubs:
    def test_knowledge_list_without_auth(self, client):
        assert client.get("/api/v1/knowledge/entries").status_code == 401

    def test_operations_list_without_auth(self, client):
        assert client.get("/api/v1/operations/aircraft").status_code == 401
