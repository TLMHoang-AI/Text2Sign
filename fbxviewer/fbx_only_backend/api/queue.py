"""
api/queue.py — Celery-backed task queue adapter cho FBX pipeline.

API interface giữ nguyên như cũ (submit, get_task, list_tasks, delete_task, TaskStatus, TaskRecord)
để convert.py, translate.py, tasks.py không cần thay đổi.

Internals:
  - submit()      → gọi Celery task, lưu metadata (fn_name, created_at) vào Redis hash fbx_task_meta
  - get_task()    → đọc Celery AsyncResult + metadata từ Redis
  - list_tasks()  → đọc danh sách task IDs từ Redis set fbx_task_ids
  - delete_task() → revoke Celery task + xóa khỏi Redis
"""

import json
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import redis.asyncio as aioredis
from .config import REDIS_HOST, REDIS_PORT

# Redis db=0 — chỉ lưu task metadata (fn_name, created_at) và danh sách task IDs
# Celery result backend dùng Redis db=1 (xem celery_app.py)
redis_client = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

_TASK_META_HASH = "fbx_task_meta"   # Hash: task_id → JSON metadata
_TASK_ID_SET    = "fbx_task_ids"    # Sorted set: task_id, score = timestamp


# ─── Enums & Records ──────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE    = "done"
    ERROR   = "error"


# Mapping từ Celery state string → TaskStatus
_CELERY_TO_STATUS = {
    "PENDING":  TaskStatus.PENDING,
    "RECEIVED": TaskStatus.PENDING,
    "STARTED":  TaskStatus.RUNNING,
    "RETRY":    TaskStatus.RUNNING,
    "SUCCESS":  TaskStatus.DONE,
    "FAILURE":  TaskStatus.ERROR,
    "REVOKED":  TaskStatus.ERROR,
}


@dataclass
class TaskRecord:
    id          : str
    status      : TaskStatus = TaskStatus.PENDING
    created_at  : str        = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at  : Optional[str] = None
    finished_at : Optional[str] = None
    result      : Optional[Any] = None
    error       : Optional[str] = None
    fn_name     : Optional[str] = None


# ─── Prometheus metrics ───────────────────────────────────────────────────────

from prometheus_client import Counter

TASKS_SUBMITTED = Counter(
    "fbx_tasks_submitted_total",
    "Total tasks submitted to the background queue",
    ["fn_name"],
)
TASKS_PROCESSED = Counter(
    "fbx_tasks_processed_total",
    "Total tasks processed by the background worker",
    ["status", "fn_name"],
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_celery_task(fn_name: str):
    """Trả về Celery task callable tương ứng với fn_name."""
    from .celery_tasks import celery_run_pipeline, celery_translate_pipeline
    _registry = {
        "run_pipeline_sync": celery_run_pipeline,
        "_translate_pipeline": celery_translate_pipeline,
    }
    task = _registry.get(fn_name)
    if task is None:
        raise ValueError(f"Function '{fn_name}' not found in Celery task registry")
    return task


def _build_record_from_celery(task_id: str, meta: dict) -> TaskRecord:
    """Xây dựng TaskRecord từ Celery AsyncResult + metadata lưu trong Redis."""
    from .celery_app import celery_app

    ar = celery_app.AsyncResult(task_id)
    celery_state = ar.state  # PENDING, STARTED, SUCCESS, FAILURE, ...
    status = _CELERY_TO_STATUS.get(celery_state, TaskStatus.PENDING)

    result = None
    error = None
    finished_at = None
    started_at = meta.get("started_at")
    fn_name = meta.get("fn_name")

    if celery_state == "SUCCESS":
        result = ar.result
        finished_at = meta.get("finished_at") or datetime.utcnow().isoformat()
    elif celery_state in ("FAILURE", "REVOKED"):
        error = str(ar.result) if ar.result else "Task failed"
        finished_at = meta.get("finished_at") or datetime.utcnow().isoformat()
    elif celery_state == "STARTED":
        started_at = meta.get("started_at") or datetime.utcnow().isoformat()

    return TaskRecord(
        id=task_id,
        status=status,
        created_at=meta.get("created_at", datetime.utcnow().isoformat()),
        started_at=started_at,
        finished_at=finished_at,
        result=result,
        error=error,
        fn_name=fn_name,
    )


# ─── Public API ───────────────────────────────────────────────────────────────

async def submit(fn_name: str, *args, **kwargs) -> str:
    """Submit một task lên Celery và trả về task_id ngay lập tức."""
    celery_task = _get_celery_task(fn_name)

    # apply_async trả về AsyncResult có .id là UUID Celery tự sinh
    async_result = celery_task.apply_async(args=list(args), kwargs=kwargs)
    task_id = async_result.id

    # Lưu metadata vào Redis
    meta = {
        "fn_name"   : fn_name,
        "created_at": datetime.utcnow().isoformat(),
    }
    score = datetime.utcnow().timestamp()

    await redis_client.hset(_TASK_META_HASH, task_id, json.dumps(meta))
    await redis_client.zadd(_TASK_ID_SET, {task_id: score})

    TASKS_SUBMITTED.labels(fn_name=fn_name).inc()
    return task_id


async def get_task(task_id: str) -> Optional[TaskRecord]:
    """Lấy trạng thái của một task theo task_id."""
    meta_str = await redis_client.hget(_TASK_META_HASH, task_id)
    if not meta_str:
        return None
    meta = json.loads(meta_str)

    loop = asyncio.get_event_loop()
    record = await loop.run_in_executor(None, _build_record_from_celery, task_id, meta)

    # Cập nhật metrics một lần khi task xong
    if record.status in (TaskStatus.DONE, TaskStatus.ERROR):
        if not meta.get("_metrics_recorded"):
            TASKS_PROCESSED.labels(
                status=record.status.value,
                fn_name=record.fn_name or "unknown"
            ).inc()
            meta["_metrics_recorded"] = True
            meta["finished_at"] = record.finished_at or datetime.utcnow().isoformat()
            await redis_client.hset(_TASK_META_HASH, task_id, json.dumps(meta))

    return record


async def list_tasks() -> list[TaskRecord]:
    """Liệt kê tất cả tasks theo thứ tự mới nhất trước."""
    # Lấy task IDs từ sorted set, score = timestamp (descending)
    task_ids = await redis_client.zrevrange(_TASK_ID_SET, 0, -1)
    if not task_ids:
        return []

    # Lấy metadata batch
    meta_list = await redis_client.hmget(_TASK_META_HASH, *task_ids)

    records = []
    for task_id, meta_str in zip(task_ids, meta_list):
        if not meta_str:
            continue
        meta = json.loads(meta_str)
        loop = asyncio.get_event_loop()
        record = await loop.run_in_executor(None, _build_record_from_celery, task_id, meta)
        records.append(record)

    return records


async def delete_task(task_id: str) -> bool:
    """Xóa task: revoke nếu đang chạy, xóa khỏi Redis."""
    exists = await redis_client.hexists(_TASK_META_HASH, task_id)
    if not exists:
        return False

    # Revoke Celery task (terminate nếu đang STARTED)
    from .celery_app import celery_app

    def _revoke():
        celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _revoke)

    await redis_client.hdel(_TASK_META_HASH, task_id)
    await redis_client.zrem(_TASK_ID_SET, task_id)
    return True


# ─── worker() stub ────────────────────────────────────────────────────────────
# Không còn asyncio worker nữa. Hàm này giữ lại để không break bất kỳ import nào.

async def worker():
    """[Deprecated] Celery worker đã thay thế asyncio worker này.
    Hàm này không làm gì — chỉ giữ lại cho backward compatibility."""
    print("[TaskQueue] Celery worker mode — asyncio worker không còn hoạt động.")
    # Không block, không loop — return ngay
