from unittest.mock import patch

from fastapi.testclient import TestClient


def test_dispatch_worker_returns_task_id(client: TestClient) -> None:
    with patch(
        "app.api.diagnostics.dispatch_test_worker",
        return_value="task-123",
    ):
        response = client.post("/diagnostics/worker")
    assert response.status_code == 200
    assert response.json() == {"task_id": "task-123"}


def test_worker_status_exposes_celery_state(client: TestClient) -> None:
    payload = {
        "task_id": "task-123",
        "state": "SUCCESS",
        "result": {"status": "ok", "task": "test_worker"},
    }
    with patch("app.api.diagnostics.get_worker_result", return_value=payload):
        response = client.get("/diagnostics/worker/task-123")
    assert response.status_code == 200
    assert response.json() == payload
