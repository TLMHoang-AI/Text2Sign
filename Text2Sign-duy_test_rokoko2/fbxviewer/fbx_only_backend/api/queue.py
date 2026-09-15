"""
api/queue.py — Async task queue (sequential, single worker) cho FBX pipeline với Redis.
"""

import asyncio
import json
import uuid
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import redis.asyncio as redis
from .config import REDIS_HOST, REDIS_PORT

# Connection to local Redis
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE    = "done"
    ERROR   = "error"


from prometheus_client import Counter

TASKS_SUBMITTED = Counter("fbx_tasks_submitted_total", "Total tasks submitted to the background queue", ["fn_name"])
TASKS_PROCESSED = Counter("fbx_tasks_processed_total", "Total tasks processed by the background worker", ["status", "fn_name"])


@dataclass
class TaskRecord:
    id         : str
    status     : TaskStatus = TaskStatus.PENDING
    created_at : str        = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at : Optional[str] = None
    finished_at: Optional[str] = None
    result     : Optional[Any] = None
    error      : Optional[str] = None
    fn_name    : Optional[str] = None
    fn_args    : list       = field(default_factory=list)
    fn_kwargs  : dict       = field(default_factory=dict)


# ─── Redis queue ──────────────────────────────────────────────────────────────

def _deserialize(data: str) -> TaskRecord:
    d = json.loads(data)
    # Coerce status string → TaskStatus enum
    d["status"] = TaskStatus(d["status"])
    return TaskRecord(**d)


async def get_task(task_id: str) -> Optional[TaskRecord]:
    data = await redis_client.hget("fbx_tasks", task_id)
    if not data:
        return None
    return _deserialize(data)


async def list_tasks() -> list[TaskRecord]:
    all_tasks = await redis_client.hgetall("fbx_tasks")
    tasks = [_deserialize(v) for v in all_tasks.values()]
    return sorted(tasks, key=lambda t: t.created_at, reverse=True)


async def delete_task(task_id: str) -> bool:
    res = await redis_client.hdel("fbx_tasks", task_id)
    return res > 0


async def submit(fn_name: str, *args, **kwargs) -> str:
    """Đưa một task vào Redis queue và trả về task_id ngay lập tức."""
    task_id = str(uuid.uuid4())
    record  = TaskRecord(
        id=task_id,
        fn_name=fn_name,
        fn_args=list(args),
        fn_kwargs=kwargs
    )
    
    await redis_client.hset("fbx_tasks", task_id, json.dumps(asdict(record)))
    await redis_client.rpush("fbx_queue", task_id)
    
    TASKS_SUBMITTED.labels(fn_name=fn_name).inc()
    return task_id


def _get_registry():
    from .pipeline import run_pipeline_sync
    from .translate import _translate_pipeline
    return {
        "run_pipeline_sync": run_pipeline_sync,
        "_translate_pipeline": _translate_pipeline,
    }

async def worker():
    """Background coroutine — chạy task tuần tự đọc từ Redis queue."""
    print("[TaskQueue] Worker started with Redis, waiting for tasks...")
    registry = None

    while True:
        # Reset mỗi vòng để tránh finally đọc giá trị cũ
        record_dict: dict | None = None
        task_id: str | None = None

        try:
            # blpop với timeout=1 → trả None nếu không có task
            res = await redis_client.blpop("fbx_queue", timeout=1)
            if not res:
                continue

            _, task_id = res
            task_data_str = await redis_client.hget("fbx_tasks", task_id)
            if not task_data_str:
                continue

            record_dict = json.loads(task_data_str)
            record_dict["status"] = TaskStatus.RUNNING.value
            record_dict["started_at"] = datetime.utcnow().isoformat()
            await redis_client.hset("fbx_tasks", task_id, json.dumps(record_dict))

            print(f"[TaskQueue] Running task {task_id}")

            if registry is None:
                registry = _get_registry()

            fn_name = record_dict.get("fn_name")
            fn = registry.get(fn_name)

            if not fn:
                raise ValueError(f"Function '{fn_name}' not found in registry")

            args   = list(record_dict.get("fn_args", []))
            kwargs = record_dict.get("fn_kwargs", {})

            if fn_name == "run_pipeline_sync" and args and isinstance(args[0], dict):
                from .models import ConvertRequest
                args[0] = ConvertRequest(**args[0])

            if asyncio.iscoroutinefunction(fn):
                result = await fn(*args, **kwargs)
            else:
                loop   = asyncio.get_event_loop()
                _args, _kwargs = args, kwargs
                result = await loop.run_in_executor(None, lambda: fn(*_args, **_kwargs))

            record_dict["result"] = result
            record_dict["status"] = TaskStatus.DONE.value

        except Exception as exc:
            traceback.print_exc()
            if record_dict is not None:
                record_dict["error"]  = str(exc)
                record_dict["status"] = TaskStatus.ERROR.value
            print(f"[TaskQueue] Task {task_id or 'unknown'} FAILED: {exc}")

        finally:
            if record_dict is not None and task_id is not None:
                record_dict["finished_at"] = datetime.utcnow().isoformat()
                await redis_client.hset("fbx_tasks", task_id, json.dumps(record_dict))
                
                status_str = record_dict.get('status', 'unknown')
                fn_name_str = record_dict.get('fn_name', 'unknown')
                TASKS_PROCESSED.labels(status=status_str, fn_name=fn_name_str).inc()
                
                print(f"[TaskQueue] Task {task_id} finished → {status_str}")
