"""Tests for FastAPI identity endpoints (Phase 02).

Tests the new tenant, login, MFA, and session validation endpoints
via the FastAPI TestClient.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from contracts.identity import UserRole
from services.core.app import app
from services.identity.auth import register_user
from services.identity.tenant import create_tenant


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


class TestIdentityEndpoints:
    def test_create_tenant_endpoint(self, client: TestClient) -> None:
        """POST /tenants creates a tenant."""
        response = client.post(
            "/tenants",
            json={"name": "API Test Tenant"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "API Test Tenant"
        assert data["is_active"] is True
        assert "tenant_id" in data

    def test_get_tenant_endpoint(self, client: TestClient) -> None:
        """GET /tenants/{id} retrieves a tenant."""
        # Create a tenant first
        create_resp = client.post(
            "/tenants",
            json={"name": "Get Test Tenant"},
        )
        tenant_id = create_resp.json()["tenant_id"]

        # Now get it
        response = client.get(f"/tenants/{tenant_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Get Test Tenant"

    def test_get_tenant_not_found(self, client: TestClient) -> None:
        """GET /tenants/{id} returns 404 for non-existent tenant."""
        response = client.get("/tenants/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_get_tenant_invalid_uuid(self, client: TestClient) -> None:
        """GET /tenants/{id} returns 400 for invalid UUID."""
        response = client.get("/tenants/not-a-uuid")
        assert response.status_code == 400

    def test_login_endpoint(self, client: TestClient) -> None:
        """POST /auth/login authenticates a user."""
        # Create tenant and user
        tenant = create_tenant(name="Login Test Tenant")
        register_user(
            tenant_id=tenant.tenant_id,
            email="login@test.com",
            password="test-password-123",
            role=UserRole.TRADER.value,
        )

        response = client.post(
            "/auth/login",
            json={
                "email": "login@test.com",
                "password": "test-password-123",
                "tenant_id": str(tenant.tenant_id),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "login@test.com"
        assert data["mfa_required"] is False
        assert "session_id" in data

    def test_login_invalid_credentials(self, client: TestClient) -> None:
        """POST /auth/login returns 401 for invalid credentials."""
        tenant = create_tenant(name="Bad Login Tenant")
        register_user(
            tenant_id=tenant.tenant_id,
            email="bad@test.com",
            password="test-password-123",
            role=UserRole.VIEWER.value,
        )

        response = client.post(
            "/auth/login",
            json={
                "email": "bad@test.com",
                "password": "wrong-password",
                "tenant_id": str(tenant.tenant_id),
            },
        )
        assert response.status_code == 401

    def test_login_invalid_tenant_id(self, client: TestClient) -> None:
        """POST /auth/login returns 400 for invalid tenant ID."""
        response = client.post(
            "/auth/login",
            json={
                "email": "test@test.com",
                "password": "password",
                "tenant_id": "not-a-uuid",
            },
        )
        assert response.status_code == 400

    def test_validate_session_endpoint(self, client: TestClient) -> None:
        """POST /sessions/validate validates a session."""
        # Create tenant, user, and login
        tenant = create_tenant(name="Session Validate Tenant")
        register_user(
            tenant_id=tenant.tenant_id,
            email="session@test.com",
            password="test-password-123",
            role=UserRole.VIEWER.value,
        )
        login_resp = client.post(
            "/auth/login",
            json={
                "email": "session@test.com",
                "password": "test-password-123",
                "tenant_id": str(tenant.tenant_id),
            },
        )
        session_id = login_resp.json()["session_id"]

        response = client.post(
            "/sessions/validate",
            json={"session_id": session_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["status"] == "active"
        assert data["is_expired"] is False

    def test_validate_session_invalid(self, client: TestClient) -> None:
        """POST /sessions/validate returns 401 for invalid session."""
        response = client.post(
            "/sessions/validate",
            json={"session_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert response.status_code == 401

    def test_mfa_setup_requires_valid_session(self, client: TestClient) -> None:
        """POST /auth/mfa/setup requires a valid session."""
        response = client.post(
            "/auth/mfa/setup",
            json={"session_id": "00000000-0000-0000-0000-000000000000", "method": "totp"},
        )
        assert response.status_code == 401

    def test_openapi_includes_identity_endpoints(self, client: TestClient) -> None:
        """Per Addendum A11: OpenAPI schema includes identity endpoints."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        paths = schema.get("paths", {})
        assert "/tenants" in paths
        assert "/auth/login" in paths
        assert "/sessions/validate" in paths
