"""Aerumentis — Integration Tests: Extended API endpoints."""
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from aerumentis.core import database as db_module
from aerumentis.core.database import Base


@pytest_asyncio.fixture
async def app_with_db():
    """Create the FastAPI app with a test database, patching module-level engine/factory."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Patch module-level objects
    orig_engine = db_module.engine
    orig_factory = db_module.async_session_factory
    db_module.engine = engine
    db_module.async_session_factory = factory

    from aerumentis.core import security as sec_module
    orig_sec_factory = sec_module.async_session_factory
    sec_module.async_session_factory = factory

    from aerumentis.main import create_app
    app = create_app()

    yield app

    db_module.engine = orig_engine
    db_module.async_session_factory = orig_factory
    sec_module.async_session_factory = orig_sec_factory
    await engine.dispose()


@pytest.fixture
def client(app_with_db):
    with TestClient(app_with_db) as c:
        yield c


@pytest.fixture
def auth_token(client):
    """Register a user and return a valid Bearer token."""
    import uuid
    unique = uuid.uuid4().hex[:8]
    response = client.post("/api/v1/auth/register", json={
        "email": f"test_{unique}@aerumentis.com",
        "password": "TestPassword123!",
        "full_name": "Test Engineer",
        "organization_name": f"TestOrg_{unique}",
        "organization_type": "airline",
    })
    assert response.status_code == 201, f"Registration failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


class TestRootAndHealth:
    def test_root_endpoint(self, client):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Aerumentis"
        assert "maintenance" in data["modules"]

    def test_health_endpoint(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("healthy", "degraded")

    def test_openapi_schema(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert schema["info"]["title"] == "Aerumentis"
        paths = schema["paths"]
        assert "/api/v1/auth/api-keys" in paths
        assert "/api/v1/chat/sessions" in paths
        assert "/api/v1/maintenance/troubleshoot" in paths


class TestAuthentication:
    def test_register_and_login(self, client):
        import uuid
        unique = uuid.uuid4().hex[:8]
        r = client.post("/api/v1/auth/register", json={
            "email": f"newuser_{unique}@aerumentis.com",
            "password": "SecurePass123!",
            "full_name": "New User",
        })
        assert r.status_code == 201, f"Register failed: {r.text}"
        tokens = r.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens

        r2 = client.post("/api/v1/auth/login", json={
            "email": f"newuser_{unique}@aerumentis.com",
            "password": "SecurePass123!",
        })
        assert r2.status_code == 200
        assert "access_token" in r2.json()

    def test_login_wrong_password(self, client):
        import uuid
        unique = uuid.uuid4().hex[:8]
        client.post("/api/v1/auth/register", json={
            "email": f"wrongpass_{unique}@aerumentis.com",
            "password": "CorrectPass123!",
            "full_name": "Test User",
        })
        r = client.post("/api/v1/auth/login", json={
            "email": f"wrongpass_{unique}@aerumentis.com",
            "password": "WrongPass456!",
        })
        assert r.status_code == 401

    def test_duplicate_registration(self, client):
        import uuid
        unique = uuid.uuid4().hex[:8]
        payload = {
            "email": f"dup_{unique}@aerumentis.com",
            "password": "Pass123!", "full_name": "Dup User",
        }
        client.post("/api/v1/auth/register", json=payload)
        r = client.post("/api/v1/auth/register", json=payload)
        assert r.status_code == 409

    def test_get_me(self, client, auth_headers):
        r = client.get("/api/v1/auth/me", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "email" in data
        assert data["role"] == "admin"

    def test_refresh_token(self, client):
        import uuid
        unique = uuid.uuid4().hex[:8]
        r = client.post("/api/v1/auth/register", json={
            "email": f"refresh_{unique}@aerumentis.com",
            "password": "Pass123!", "full_name": "Refresh User",
        })
        refresh_token = r.json()["refresh_token"]
        r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert r2.status_code == 200
        assert "access_token" in r2.json()


class TestAPIKeys:
    def test_create_api_key(self, client, auth_headers):
        r = client.post("/api/v1/auth/api-keys", json={"name": "test-key"}, headers=auth_headers)
        assert r.status_code == 201, f"Create failed: {r.text}"
        data = r.json()
        assert data["name"] == "test-key"
        assert data["key"].startswith("aer_")
        assert data["key_prefix"] == data["key"][:12]

    def test_list_api_keys(self, client, auth_headers):
        client.post("/api/v1/auth/api-keys", json={"name": "list-test"}, headers=auth_headers)
        r = client.get("/api/v1/auth/api-keys", headers=auth_headers)
        assert r.status_code == 200
        keys = r.json()
        assert len(keys) >= 1
        assert all("key" not in k for k in keys)

    def test_revoke_api_key(self, client, auth_headers):
        create_r = client.post("/api/v1/auth/api-keys", json={"name": "revoke-test"}, headers=auth_headers)
        key_id = create_r.json()["id"]
        r = client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=auth_headers)
        assert r.status_code == 200

    def test_api_keys_require_auth(self, client):
        assert client.get("/api/v1/auth/api-keys").status_code == 401


class TestDocuments:
    def test_upload_unsupported_type(self, client, auth_headers):
        r = client.post("/api/v1/documents/upload",
                        headers=auth_headers,
                        files={"file": ("test.exe", b"fake content", "application/octet-stream")})
        assert r.status_code == 415

    def test_upload_empty_file(self, client, auth_headers):
        r = client.post("/api/v1/documents/upload",
                        headers=auth_headers,
                        files={"file": ("empty.txt", b"", "text/plain")})
        assert r.status_code == 400

    def test_documents_require_auth(self, client):
        assert client.get("/api/v1/documents/").status_code == 401

    def test_document_stats_require_auth(self, client):
        assert client.get("/api/v1/documents/stats/summary").status_code == 401


class TestChat:
    def test_chat_query_requires_auth(self, client):
        r = client.post("/api/v1/chat/query", json={"question": "How do I replace a hydraulic pump?"})
        assert r.status_code == 401

    def test_chat_query_short_question(self, client, auth_headers):
        r = client.post("/api/v1/chat/query", json={"question": "ab"}, headers=auth_headers)
        assert r.status_code == 422

    def test_chat_sessions_require_auth(self, client):
        assert client.get("/api/v1/chat/sessions").status_code == 401


class TestMaintenance:
    def test_troubleshoot_requires_auth(self, client):
        r = client.post("/api/v1/maintenance/troubleshoot",
                       json={"symptom": "hydraulic pressure low"})
        assert r.status_code == 401

    def test_search_requires_auth(self, client):
        r = client.get("/api/v1/maintenance/search?q=hydraulic+pump")
        assert r.status_code == 401


class TestModuleStubs:
    def test_knowledge_list_without_auth(self, client):
        assert client.get("/api/v1/knowledge/entries").status_code == 401

    def test_operations_list_without_auth(self, client):
        assert client.get("/api/v1/operations/aircraft").status_code == 401
