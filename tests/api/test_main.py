"""Tests for the FastAPI application."""

import pytest
from fastapi.testclient import TestClient

from autovalor import __version__
from autovalor.api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_reports_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_model_info_describes_the_served_model(client: TestClient) -> None:
    response = client.get("/model-info")
    assert response.status_code == 200
    body = response.json()
    assert body["target"] == "log_price"
    assert body["vehicle_types"] == ["car", "motorcycle"]
