from unittest.mock import patch

from fastapi.testclient import TestClient

from app.services.dependencies import DependencyReport


def test_dependencies_success(client: TestClient) -> None:
    report = DependencyReport(postgres=True, redis=True)
    with patch("app.api.health.probe_dependencies", return_value=report):
        response = client.get("/health/dependencies")
    assert response.status_code == 200
    assert response.json() == {"postgres": "ok", "redis": "ok"}


def test_dependencies_postgres_failure_returns_503(client: TestClient) -> None:
    report = DependencyReport(postgres=False, redis=True)
    with patch("app.api.health.probe_dependencies", return_value=report):
        response = client.get("/health/dependencies")
    assert response.status_code == 503
    assert response.json() == {"postgres": "error", "redis": "ok"}


def test_dependencies_redis_failure_returns_503(client: TestClient) -> None:
    report = DependencyReport(postgres=True, redis=False)
    with patch("app.api.health.probe_dependencies", return_value=report):
        response = client.get("/health/dependencies")
    assert response.status_code == 503
    assert response.json() == {"postgres": "ok", "redis": "error"}
