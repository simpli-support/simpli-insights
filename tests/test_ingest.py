"""Tests for data ingest endpoints."""

import io
import json

import pytest
from fastapi.testclient import TestClient

from simpli_insights.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_ingest_csv(client: TestClient) -> None:
    csv_content = (
        "id,subject,content\n"
        "c-1,Password reset,I need to reset my password\n"
        "c-2,Billing issue,I was charged twice\n"
        "c-3,Login problem,Cannot access my account\n"
    )
    file = io.BytesIO(csv_content.encode())
    response = client.post(
        "/api/v1/ingest",
        files={"file": ("cases.csv", file, "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["processed"] == 3


def test_ingest_json(client: TestClient) -> None:
    records = [
        {"id": "c-1", "subject": "Help", "content": "Need help"},
        {"id": "c-2", "subject": "Bug", "content": "Found a bug"},
        {"id": "c-3", "subject": "Question", "content": "How do I..."},
    ]
    file = io.BytesIO(json.dumps(records).encode())
    response = client.post(
        "/api/v1/ingest",
        files={"file": ("cases.json", file, "application/json")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["processed"] == 3


def test_ingest_with_custom_mappings(client: TestClient) -> None:
    csv_content = (
        "case_id,title,body\n"
        "1,Issue A,Details A\n"
        "2,Issue B,Details B\n"
        "3,Issue C,Details C\n"
    )
    mappings = json.dumps([
        {"source": "case_id", "target": "id"},
        {"source": "title", "target": "subject"},
        {"source": "body", "target": "content"},
    ])
    file = io.BytesIO(csv_content.encode())
    response = client.post(
        "/api/v1/ingest",
        files={"file": ("data.csv", file, "text/csv")},
        data={"mappings": mappings},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["processed"] == 3


def test_ingest_salesforce_missing_credentials(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ingest/salesforce",
        json={"limit": 10},
    )
    assert response.status_code == 400
    assert "credentials" in response.json()["detail"].lower()
