"""
api/celery_tasks.py — Celery task definitions cho FBX pipeline backend.

Requires: celery[redis] (in requirements_api.txt)

Các task này wrap các pipeline functions hiện có để có thể chạy qua Celery worker.
Tương thích song song với asyncio queue (queue.py) — không thay thế, chỉ bổ sung.

Cách dùng:
  # Submit task async (fire-and-forget, trả Celery AsyncResult)
  result = celery_run_pipeline.delay(req_dict)
  result = celery_translate_pipeline.delay(sentence, record_id=42)

  # Lấy kết quả
  result.get(timeout=3600)

  # Check status
  result.status  # PENDING | STARTED | SUCCESS | FAILURE | RETRY | REVOKED
"""

from typing import Optional
from celery import Task
from celery.utils.log import get_task_logger
from prometheus_client import Counter

from .celery_app import celery_app

logger = get_task_logger(__name__)

# ─── Prometheus metrics ───────────────────────────────────────────────────────

CELERY_TASKS_SUBMITTED = Counter(
    "fbx_celery_tasks_submitted_total",
    "Total Celery tasks submitted",
    ["task_name"],
)
CELERY_TASKS_PROCESSED = Counter(
    "fbx_celery_tasks_processed_total",
    "Total Celery tasks processed",
    ["task_name", "status"],
)


# ─── Base Task class ──────────────────────────────────────────────────────────

class FBXBaseTask(Task):
    """Base task class với Prometheus metrics và logging."""

    abstract = True

    def on_success(self, retval, task_id, args, kwargs):
        logger.info("[Celery] Task %s SUCCESS", task_id)
        CELERY_TASKS_PROCESSED.labels(task_name=self.name, status="success").inc()

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error("[Celery] Task %s FAILED: %s", task_id, exc)
        CELERY_TASKS_PROCESSED.labels(task_name=self.name, status="failure").inc()

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning("[Celery] Task %s RETRY: %s", task_id, exc)
        CELERY_TASKS_PROCESSED.labels(task_name=self.name, status="retry").inc()


# ─── Task definitions ─────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    base=FBXBaseTask,
    name="fbxviewer.run_pipeline",
    max_retries=2,
    default_retry_delay=60,
)
def celery_run_pipeline(self, req_dict: dict) -> dict:
    """
    Chạy toàn bộ SMPL-X → AMASS → Blender retarget → FBX pipeline.

    Args:
        req_dict: dict tương ứng với ConvertRequest.model_dump()

    Returns:
        dict với keys: status, output_files, log
    """
    logger.info("[Celery] celery_run_pipeline started, task_id=%s", self.request.id)
    CELERY_TASKS_SUBMITTED.labels(task_name=self.name).inc()

    try:
        from .pipeline import run_pipeline_sync
        from .models import ConvertRequest

        req = ConvertRequest(**req_dict)
        result = run_pipeline_sync(req)

        if result.get("status") == "error":
            raise RuntimeError(result.get("error", "Pipeline failed"))

        return result

    except Exception as exc:
        logger.exception("[Celery] celery_run_pipeline error: %s", exc)
        # Retry với exponential backoff nếu lỗi không phải ValueError
        if not isinstance(exc, (ValueError, TypeError)):
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        raise


@celery_app.task(
    bind=True,
    base=FBXBaseTask,
    name="fbxviewer.translate_pipeline",
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=3600,
    time_limit=3900,
)
def celery_translate_pipeline(self, sentence: str, record_id: Optional[int] = None) -> dict:
    """
    Chạy translate text → AMASS → Blender retarget → FBX pipeline.

    Args:
        sentence:  Câu văn bản cần dịch
        record_id: ID trong DB để cập nhật status sau khi xong (optional)

    Returns:
        dict với keys: status, items, output_files, subtitle_text, subtitle_timings
    """
    logger.info(
        "[Celery] celery_translate_pipeline started, task_id=%s, sentence=%r",
        self.request.id,
        sentence[:60] if len(sentence) > 60 else sentence,
    )
    CELERY_TASKS_SUBMITTED.labels(task_name=self.name).inc()

    try:
        from .translate import _translate_pipeline

        result = _translate_pipeline(sentence, record_id=record_id)

        if result.get("status") == "error":
            raise RuntimeError(result.get("error", "Translate pipeline failed"))

        return result

    except Exception as exc:
        logger.exception("[Celery] celery_translate_pipeline error: %s", exc)
        if not isinstance(exc, (ValueError, TypeError)):
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        raise
