"""
api/celery_app.py — Celery application instance cho FBX pipeline backend.

Sử dụng Redis làm broker và result backend (DB 1 để tách biệt với asyncio queue ở DB 0).
"""

from celery import Celery
from .config import REDIS_HOST, REDIS_PORT

CELERY_BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"
CELERY_RESULT_BACKEND = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"

celery_app = Celery(
    "fbxviewer",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["api.celery_tasks"],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task behavior
    task_track_started=True,
    task_acks_late=True,           # Ack sau khi task hoàn thành → an toàn hơn nếu worker crash
    worker_prefetch_multiplier=1,  # Phù hợp cho heavy, long-running tasks

    # Result expiry — giữ kết quả 24h
    result_expires=86400,

    # Task time limits
    task_soft_time_limit=3600,    # 1 giờ soft limit (raise SoftTimeLimitExceeded)
    task_time_limit=3900,         # 5 phút grace period sau soft limit rồi SIGKILL

    # Retry defaults
    task_max_retries=3,
    task_default_retry_delay=30,  # 30 giây giữa các lần retry
)
