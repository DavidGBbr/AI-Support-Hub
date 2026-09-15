from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("ai_support_hub")
celery_app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_always_eager=False,
    task_track_started=True,
)

from app.tasks.test_worker import test_worker as _test_worker  # noqa: E402, F401
