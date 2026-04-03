"""Tests for the FastAPI application."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from simpli_insights.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _case(
    id: str = "c-1", subject: str = "Test", content: str = "Test content"
) -> dict:
    return {"id": id, "subject": subject, "content": content}


# ---------------------------------------------------------------------------
# Health (unversioned)
# ---------------------------------------------------------------------------


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------


def test_themes(client: TestClient) -> None:
    cases = [_case(id=f"c-{i}") for i in range(3)]
    response = client.post("/api/v1/themes", json={"cases": cases})
    assert response.status_code == 200
    data = response.json()
    assert "audit_id" in data
    assert data["total_cases"] == 3
    assert isinstance(data["themes"], list)
    assert isinstance(data["uncategorized_case_ids"], list)
    assert len(data["uncategorized_case_ids"]) == 3


def test_themes_too_few(client: TestClient) -> None:
    cases = [_case(id=f"c-{i}") for i in range(2)]
    response = client.post("/api/v1/themes", json={"cases": cases})
    assert response.status_code == 422


def test_themes_missing_id(client: TestClient) -> None:
    response = client.post(
        "/api/v1/themes",
        json={"cases": [{"subject": "X", "content": "Y"}] * 3},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Emerging
# ---------------------------------------------------------------------------


def test_emerging(client: TestClient) -> None:
    response = client.post(
        "/api/v1/emerging",
        json={"recent_cases": [_case()]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "audit_id" in data
    assert data["total_recent"] == 1
    assert data["total_baseline"] is None
    assert isinstance(data["topics"], list)


def test_emerging_with_baseline(client: TestClient) -> None:
    response = client.post(
        "/api/v1/emerging",
        json={
            "recent_cases": [_case(id="r-1")],
            "baseline_cases": [_case(id="b-1"), _case(id="b-2")],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_recent"] == 1
    assert data["total_baseline"] == 2


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


def test_categories(client: TestClient) -> None:
    cases = [_case(id=f"c-{i}") for i in range(3)]
    response = client.post("/api/v1/categories", json={"cases": cases})
    assert response.status_code == 200
    data = response.json()
    assert "audit_id" in data
    assert data["total_cases"] == 3
    assert isinstance(data["categories"], list)
    assert len(data["unmapped_case_ids"]) == 3


def test_categories_with_existing(client: TestClient) -> None:
    cases = [_case(id=f"c-{i}") for i in range(3)]
    response = client.post(
        "/api/v1/categories",
        json={"cases": cases, "existing_categories": ["billing", "technical"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_cases"] == 3


# ---------------------------------------------------------------------------
# Distribution
# ---------------------------------------------------------------------------


def test_distribution(client: TestClient) -> None:
    response = client.post(
        "/api/v1/distribution",
        json={"cases": [_case()]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "audit_id" in data
    assert data["total_cases"] == 1
    assert data["uncategorized_count"] == 1
    assert isinstance(data["distribution"], list)


# ---------------------------------------------------------------------------
# Request ID middleware
# ---------------------------------------------------------------------------


def test_request_id_generated(client: TestClient) -> None:
    response = client.get("/health")
    assert "x-request-id" in response.headers


def test_request_id_forwarded(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "custom-123"})
    assert response.headers["x-request-id"] == "custom-123"


# ---------------------------------------------------------------------------
# OpenAPI schema
# ---------------------------------------------------------------------------


def test_openapi_schema(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/api/v1/themes" in schema["paths"]
    assert "/api/v1/emerging" in schema["paths"]
    assert "/api/v1/categories" in schema["paths"]
    assert "/api/v1/distribution" in schema["paths"]
    assert "/health" in schema["paths"]
