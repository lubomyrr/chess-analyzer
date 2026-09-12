from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "chess_analyzer",
    broker=settings.celery_broker_url,
    include=["app.workers.analyze_game"],
)

celery_app.conf.update(
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_serializer="json",
    task_track_started=True,
    worker_prefetch_multiplier=1,
)
