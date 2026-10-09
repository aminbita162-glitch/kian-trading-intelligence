"""Tests for FastAPI health and root endpoints.

Uses FastAPI TestClient (httpx-based) to verify the API foundation.
"""

import pytest
from fastapi.testclient import TestClient

from services.core.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


class TestHealthEndpoints:
    def test_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_service_info(self, client: TestClient) -> None:
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "kian-trading-intelligence"
        assert "version" in data
        assert "timestamp" in data

    def test_health_identifies_operating_mode(self, client: TestClient) -> None:
        """Per AD-003/Section 01.3: mode must be clearly identified."""
        response = client.get("/health")
        data = response.json()
        assert "operating_mode" in data
        assert data["operating_mode"] == "simulation"
        assert data["is_live"] is False

    def test_readiness_returns_200(self, client: TestClient) -> None:
        response = client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"

    def test_root_returns_metadata(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Kian Trading Intelligence API"
        assert "version" in data
        assert "docs" in data

    def test_openapi_schema_available(self, client: TestClient) -> None:
        """Per Addendum A11: OpenAPI schema must be available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert data["info"]["title"] == "Kian Trading Intelligence API"

    def test_docs_endpoint_available(self, client: TestClient) -> None:
        """Per Addendum A11: Swagger UI must be available at /docs."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_endpoint_available(self, client: TestClient) -> None:
        """Per Addendum A11: ReDoc must be available at /redoc."""
        response = client.get("/redoc")
        assert response.status_code == 200
