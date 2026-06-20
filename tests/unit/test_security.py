"""Aerumentis — Unit Tests: Security."""
import pytest
from aerumentis.core.security import (
    AuthenticatedUser, Permission, UserRole, create_access_token, create_refresh_token,
    create_token_pair, decode_token, generate_api_key, has_permission,
)


class TestJWTTokens:
    def test_create_and_decode_access_token(self):
        token = create_access_token(user_id="test-user-id", role=UserRole.ENGINEER, org_id="test-org", email="e@t.com")
        data = decode_token(token)
        assert data.sub == "test-user-id"
        assert data.role == UserRole.ENGINEER
        assert data.org_id == "test-org"
        assert data.jti is not None

    def test_create_and_decode_refresh_token(self):
        token = create_refresh_token(user_id="test-user-id", role=UserRole.ADMIN, org_id="test-org")
        data = decode_token(token)
        assert data.sub == "test-user-id"
        assert data.role == UserRole.ADMIN

    def test_token_pair(self):
        pair = create_token_pair(user_id="test-user-id", role=UserRole.ADMIN)
        assert pair.access_token
        assert pair.refresh_token
        assert pair.token_type == "bearer"
        assert pair.expires_in > 0

    def test_invalid_token_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_token("invalid.token.here")
        assert exc_info.value.status_code == 401

    def test_expired_token_raises(self):
        from fastapi import HTTPException
        token = create_access_token(user_id="test-user", role=UserRole.VIEWER, expires_minutes=-1)
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()


class TestPermissions:
    def test_superadmin_has_all_permissions(self):
        for perm in Permission:
            assert has_permission(UserRole.SUPERADMIN, perm)

    def test_admin_has_document_permissions(self):
        assert has_permission(UserRole.ADMIN, Permission.DOCUMENT_UPLOAD)
        assert has_permission(UserRole.ADMIN, Permission.DOCUMENT_DELETE)

    def test_viewer_cannot_upload(self):
        assert not has_permission(UserRole.VIEWER, Permission.DOCUMENT_UPLOAD)

    def test_maintenance_tech_can_query_rag(self):
        assert has_permission(UserRole.MAINTENANCE_TECH, Permission.RAG_QUERY)
        assert has_permission(UserRole.MAINTENANCE_TECH, Permission.KNOWLEDGE_WRITE)

    def test_ground_ops_can_manage_ops(self):
        assert has_permission(UserRole.GROUND_OPS, Permission.OPS_MANAGE)

    def test_viewer_can_read(self):
        assert has_permission(UserRole.VIEWER, Permission.DOCUMENT_READ)
        assert has_permission(UserRole.VIEWER, Permission.RAG_QUERY)


class TestAPIKeys:
    def test_generate_api_key_format(self):
        key = generate_api_key()
        assert key.startswith("aer_")
        assert len(key) > 20

    def test_generate_api_key_uniqueness(self):
        assert generate_api_key() != generate_api_key()
