"""
blender_server.py — Blender persistent socket server.

Chạy trong Blender --background, lắng nghe TCP port 9999, nhận JSON command,
thực hiện retarget rồi gửi kết quả JSON lại. Giữ Blender luôn warm.

Cách khởi động (do FastAPI tự gọi khi startup):
  blender --background --python blender_server.py -- --port 9999

Protocol (mỗi message kết thúc bằng newline \n):
  Request:  {"type": "retarget", "amass": "...", "xbot": "...", "out": "...",
             "fps": 30, "stabilize": true, "rotate_x": -90.0}
  Response: {"status": "ok", "out": "..."} hoặc {"status": "error", "error": "..."}
  Shutdown: {"type": "shutdown"}
"""

import sys
import os
import json
import socket
import traceback

try:
    import bpy  # noqa: F401
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False

PORT_DEFAULT = 9999


def parse_args():
    try:
        idx  = sys.argv.index("--")
        argv = sys.argv[idx + 1:]
    except ValueError:
        argv = []
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=PORT_DEFAULT)
    return p.parse_args(argv)


# ─── Blender retarget (reuse từ blender_retarget_auto) ───────────────────────

def _run_retarget(cmd: dict) -> dict:
    """Thực hiện retarget trong Blender context."""
    import importlib, types

    # Dynamic import blender_retarget_auto để tái sử dụng run_in_blender()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, "blender_retarget_auto.py")

    loader = importlib.machinery.SourceFileLoader("bra", script_path)
    mod    = types.ModuleType("bra")
    mod.__file__ = script_path
    loader.exec_module(mod)

    # Fake args object
    class _Args:
        stabilize = cmd.get("stabilize", False)
        rotate_x  = cmd.get("rotate_x", 0.0)

    mod.args = _Args()

    amass = cmd["amass"]
    xbot  = cmd["xbot"]
    out   = cmd["out"]
    fps   = cmd.get("fps", 30.0)

    mod.run_in_blender(amass_path=amass, xbot_fbx=xbot, output_fbx=out, fps=fps)
    return {"status": "ok", "out": out}


# ─── Socket server ────────────────────────────────────────────────────────────

def run_server(port: int):
    print(f"[BlenderServer] Listening on 127.0.0.1:{port} ...", flush=True)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)

    while True:
        conn, addr = srv.accept()
        print(f"[BlenderServer] Connection from {addr}", flush=True)
        try:
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk

            cmd = json.loads(data.decode())

            if cmd.get("type") == "shutdown":
                print("[BlenderServer] Shutdown signal received.", flush=True)
                conn.sendall(json.dumps({"status": "ok", "msg": "bye"}).encode() + b"\n")
                conn.close()
                break

            result = _run_retarget(cmd)
            conn.sendall(json.dumps(result).encode() + b"\n")

        except Exception as exc:
            tb  = traceback.format_exc()
            err = {"status": "error", "error": str(exc), "traceback": tb}
            print(f"[BlenderServer] ERROR: {exc}", flush=True)
            try:
                conn.sendall(json.dumps(err).encode() + b"\n")
            except Exception:
                pass
        finally:
            conn.close()

    srv.close()
    print("[BlenderServer] Server closed.", flush=True)


# ─── Entry point ─────────────────────────────────────────────────────────────

if IN_BLENDER:
    args = parse_args()
    run_server(args.port)
else:
    print("❌ Script này phải chạy bên trong Blender (--background).")
    sys.exit(1)
