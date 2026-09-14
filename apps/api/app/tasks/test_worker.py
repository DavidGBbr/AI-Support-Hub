from app.core.celery import celery_app


@celery_app.task(name="test_worker")
def test_worker() -> dict[str, str]:
    return {"status": "ok", "task": "test_worker"}
