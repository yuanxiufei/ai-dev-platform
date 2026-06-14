from celery import Celery
from .redis_config import REDIS_URL

celery_app = Celery(
    "ai_fullstack",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["workers.code_worker", "workers.video_worker"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
