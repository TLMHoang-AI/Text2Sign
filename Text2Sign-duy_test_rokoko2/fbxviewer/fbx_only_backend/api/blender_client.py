"""
api/blender_client.py — Client kết nối đến blender_server.py qua TCP socket.

FastAPI gọi send_retarget_cmd() thay vì spawn Blender process mới.
Blender server phải đang chạy (do lifespan startup event khởi động).
"""

import json
import socket
import subprocess
import time
import os
import sys
from pathlib import Path

from .config import _HERE
from .helpers import find_blender

BLENDER_SERVER_PORT   = 9999
BLENDER_SERVER_HOST   = "127.0.0.1"
BLENDER_SERVER_SCRIPT = str(_HERE / "blender_server.py")

_blender_proc: subprocess.Popen | None = None


# ─── Lifecycle ────────────────────────────────────────────────────────────────

def start_blender_server():
    """Khởi động Blender server ở background khi FastAPI startup."""
    global _blender_proc

    if _is_server_alive():
        print("[BlenderClient] Server đã chạy sẵn.")
        return

    blender_bin = os.environ.get("BLENDER_BIN") or find_blender()
    cmd = [
        blender_bin, "--background",
        "--python", BLENDER_SERVER_SCRIPT,
        "--",
        "--port", str(BLENDER_SERVER_PORT),
    ]
    print(f"[BlenderClient] Khởi động Blender server: {' '.join(cmd)}")
    _blender_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(_HERE),
    )

    # Đợi Blender sẵn sàng (tối đa 60s)
    for i in range(60):
        time.sleep(1)
        if _is_server_alive():
            print(f"[BlenderClient] Blender server ready (sau {i+1}s) ✅")
            return

    print("[BlenderClient] ⚠ Blender server chưa sẵn sàng sau 60s — pipeline fallback sẽ spawn process mới.")


def stop_blender_server():
    """Gửi shutdown signal khi FastAPI shutdown."""
    global _blender_proc
    try:
        _send({"type": "shutdown"})
    except Exception:
        pass
    if _blender_proc:
        _blender_proc.terminate()
        _blender_proc = None
    print("[BlenderClient] Blender server stopped.")


def _is_server_alive() -> bool:
    try:
        with socket.create_connection((BLENDER_SERVER_HOST, BLENDER_SERVER_PORT), timeout=1):
            return True
    except OSError:
        return False


# ─── Send command ─────────────────────────────────────────────────────────────

def _send(cmd: dict) -> dict:
    """Gửi JSON command đến Blender server, nhận response."""
    payload = json.dumps(cmd).encode() + b"\n"
    with socket.create_connection((BLENDER_SERVER_HOST, BLENDER_SERVER_PORT), timeout=300) as sock:
        sock.sendall(payload)
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    return json.loads(data.decode())


def send_retarget_cmd(
    amass_npz: str,
    output_fbx: str,
    xbot_fbx: str,
    fps: float,
    stabilize: bool,
    rotate_x: float,
) -> dict:
    """
    Gửi lệnh retarget đến Blender server đang warm.
    Nếu server không alive → raise RuntimeError (pipeline fallback sẽ xử lý).
    """
    if not _is_server_alive():
        raise RuntimeError("Blender server chưa sẵn sàng.")

    cmd = {
        "type"     : "retarget",
        "amass"    : amass_npz,
        "xbot"     : xbot_fbx,
        "out"      : output_fbx,
        "fps"      : fps,
        "stabilize": stabilize,
        "rotate_x" : rotate_x,
    }
    result = _send(cmd)
    if result.get("status") != "ok":
        raise RuntimeError(result.get("error", "Blender retarget thất bại"))
    return result
