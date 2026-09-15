#!/usr/bin/env python3
"""
main.py — FastAPI REST API cho FBX pipeline (fbx-viewer backend)

Endpoints:
  GET  /                   — Health check
  GET  /clips              — Liệt kê folder trong output_smplerx/
  POST /convert            — Submit pipeline → trả task_id ngay
  GET  /fbx                — Liệt kê các file .fbx đã output
  GET  /fbx/{filename}     — Download file FBX
  POST /translate          — Submit translate pipeline → trả task_id ngay
  GET  /tasks              — List tất cả tasks
  GET  /tasks/{task_id}    — Poll trạng thái task
  DELETE /tasks/{task_id}  — Xóa task

Task execution: Celery workers (xem docker-compose.yml → celery_worker service)

Chạy:
  uvicorn main:app --host 0.0.0.0 --port 8000
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from api import clips, fbx, convert, translate, tasks, users
from api import queue as tq
from api.db import init_db
from api.blender_client import start_blender_server, stop_blender_server


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("[Startup] Khởi tạo database...")
    await init_db()

    print("[Startup] Celery worker đang xử lý tasks (xem celery_worker container)...")

    print("[Startup] Khởi động Blender warm server...")
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, start_blender_server)

    yield

    # Shutdown
    print("[Shutdown] Dừng Blender server...")
    stop_blender_server()
    print("[Shutdown] Done.")


# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Text2Sign FBX Pipeline API",
    description="API để convert SMPL-X → AMASS → Blender retarget → FBX",
    version="1.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thêm metrics Prometheus
Instrumentator().instrument(app).expose(app)

app.include_router(clips.router)
app.include_router(fbx.router)
app.include_router(convert.router)
app.include_router(translate.router)
app.include_router(tasks.router)
app.include_router(users.router)


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/", summary="Health check")
def root():
    return {"service": "Text2Sign FBX Pipeline API", "version": "1.2.0"}


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("Starting FBX Backend API on http://localhost:8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
