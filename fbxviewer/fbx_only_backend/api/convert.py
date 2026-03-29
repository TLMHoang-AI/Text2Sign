"""
api/convert.py — Endpoint POST /convert: submit pipeline vào task queue.
Trả task_id ngay, client poll GET /tasks/{id} để lấy kết quả.
"""

from fastapi import APIRouter
from .models import ConvertRequest
from .pipeline import run_pipeline_sync
from . import queue as tq

router = APIRouter()


@router.post("/convert", summary="Chạy pipeline SMPL-X → AMASS → FBX (async, trả task_id ngay)")
async def convert(req: ConvertRequest):
    req_dict = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    task_id = await tq.submit("run_pipeline_sync", req_dict)
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}
