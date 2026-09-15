from typing import Any

from celery.result import AsyncResult

from app.core.celery import celery_app
from app.tasks.test_worker import test_worker


def dispatch_test_worker() -> str:
    result = test_worker.delay()
    return str(result.id)


def get_worker_result(task_id: str) -> dict[str, Any]:
    async_result = AsyncResult(task_id, app=celery_app)
    payload: dict[str, Any] = {
        "task_id": task_id,
        "state": async_result.state,
        "result": None,
    }
    if not async_result.ready():
        return payload
    if async_result.failed():
        payload["result"] = {"error": str(async_result.result)}
        return payload
    payload["result"] = async_result.result
    return payload
