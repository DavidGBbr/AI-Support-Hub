from typing import Any

from fastapi import APIRouter

from app.services.worker import dispatch_test_worker, get_worker_result

router = APIRouter(prefix="/diagnostics")


@router.post("/worker")
def create_worker_diagnostic() -> dict[str, str]:
    return {"task_id": dispatch_test_worker()}


@router.get("/worker/{task_id}")
def read_worker_diagnostic(task_id: str) -> dict[str, Any]:
    return get_worker_result(task_id)
