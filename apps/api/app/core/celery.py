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
    broker_connection_timeout=3,
    broker_transport_options={"socket_connect_timeout": 3, "socket_timeout": 5},
)

from app.tasks.document_ingestion import (  # noqa: E402
    process_document_task as _process_document_task,  # noqa: F401
)
from app.tasks.test_worker import test_worker as _test_worker  # noqa: E402, F401
