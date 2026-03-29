"""
api/tasks.py — Endpoints để poll task status từ queue.

  GET  /tasks              — list tất cả tasks
  GET  /tasks/{task_id}    — poll status + result của một task
  DELETE /tasks/{task_id}  — xóa task
"""

from fastapi import APIRouter, HTTPException
from . import queue as tq
from .queue import TaskStatus

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", summary="List tất cả tasks")
async def list_tasks():
    tasks = await tq.list_tasks()
    return {
        "count": len(tasks),
        "tasks": [
            {
                "id"          : t.id,
                "status"      : t.status,
                "created_at"  : t.created_at,
                "started_at"  : t.started_at,
                "finished_at" : t.finished_at,
            }
            for t in tasks
        ],
    }


@router.get("/{task_id}", summary="Poll trạng thái và kết quả của một task")
async def get_task(task_id: str):
    record = await tq.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' không tồn tại")

    resp = {
        "id"          : record.id,
        "status"      : record.status,
        "created_at"  : record.created_at,
        "started_at"  : record.started_at,
        "finished_at" : record.finished_at,
    }
    if record.status == TaskStatus.DONE:
        resp["result"] = record.result
    elif record.status == TaskStatus.ERROR:
        resp["error"] = record.error
    return resp


@router.delete("/{task_id}", summary="Xóa task khỏi danh sách")
async def delete_task(task_id: str):
    success = await tq.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' không tồn tại")
    return {"deleted": task_id}
