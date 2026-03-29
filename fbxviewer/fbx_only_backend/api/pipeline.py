"""
api/pipeline.py — Các hàm runner pipeline: convert SMPL-X → AMASS, merge, retarget Blender.
"""

import os
import json
import tempfile
from pathlib import Path

from .config import _HERE, DEFAULT_AMASS_DIR, DEFAULT_OUTPUT_DIR, DEFAULT_XBOT_FBX
from .helpers import (
    make_logger,
    find_blender,
    build_batch_convert_cmd,
    collect_amass_pairs,
    run_cmd,
    build_blender_batch_payload,
)
from .models import ConvertRequest


# ─── Run pipeline sync ────────────────────────────────────────────────────────

def run_pipeline_sync(req: ConvertRequest):
    """Chạy toàn bộ pipeline đồng bộ và trả về kết quả."""
    results_log = []
    log = make_logger(results_log)
    output_files = []

    try:
        # ── Bước 1: batch_convert_amass ───────────────────────────────────
        log("=" * 60)
        log("BƯỚC 1: Batch convert SMPL-X → AMASS .npz")
        log("=" * 60)

        amass_dir = str(DEFAULT_AMASS_DIR)
        os.makedirs(amass_dir, exist_ok=True)

        cmd1, also_merge = build_batch_convert_cmd(req, amass_dir)
        proc1 = run_cmd(cmd1, _HERE, log)

        if proc1.returncode != 0:
            raise RuntimeError(f"batch_convert_amass.py thất bại (code {proc1.returncode})")

        amass_pairs = collect_amass_pairs(req, amass_dir, also_merge)
        log(f"\n→ Tìm thấy {len(amass_pairs)} file(s) để retarget.\n")

        # ── Bước 2: Blender retarget ──────────────────────────────────────
        log("=" * 60)
        log("BƯỚC 2: Blender Retarget")
        log("=" * 60)

        blender_bin = req.blender_bin
        if not blender_bin or str(blender_bin).lower() == "string":
            blender_bin = os.environ.get("BLENDER_BIN") or find_blender()

        log(f"Blender: {blender_bin}\n")

        output_dir = DEFAULT_OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)

        script_retarget = str(_HERE / "blender_retarget_auto.py")
        xbot_fbx        = str(DEFAULT_XBOT_FBX.resolve())

        payload, batch_items = build_blender_batch_payload(amass_pairs, output_dir, req, xbot_fbx)

        if batch_items:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".json",
                delete=False,
                dir=str(_HERE),
                encoding="utf-8",
            ) as f:
                json.dump(payload, f)
                batch_path = f.name

            cmd2 = [
                blender_bin, "--background",
                "--python", script_retarget,
                "--",
                "--batch-json", batch_path,
                "--xbot", xbot_fbx,
                "--fps", str(req.fps),
            ]
            if req.stabilize:   cmd2.append("--stabilize")
            if req.rotate_x != 0.0:
                cmd2 += ["--rotate-x", str(req.rotate_x)]

            log(f"\n  Blender batch: {len(batch_items)} clip(s)")
            try:
                proc2 = run_cmd(cmd2, _HERE, log)

                if proc2.returncode == 0:
                    for item in batch_items:
                        if item.get("skip"):
                            log(f"  ⏭ Bỏ qua (đã có): {item['clip']}_xbot.fbx")
                        output_files.append(f"{item['clip']}_xbot.fbx")
                    log(f"  ✅ Batch OK ({len(batch_items)} file(s))")
                else:
                    log(f"  ❌ Batch FAILED (returncode={proc2.returncode})")
                    raise RuntimeError(f"Blender batch failed (returncode={proc2.returncode})")
            finally:
                try:
                    os.unlink(batch_path)
                except OSError:
                    pass

        if not output_files:
            raise RuntimeError("Pipeline không xuất ra file FBX.")

        return {
            "status": "success",
            "output_files": output_files,
            "log": "\n".join(results_log)
        }

    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "log": "\n".join(results_log) + f"\n❌ LỖI: {exc}"
        }


# ─── Run batch convert only ───────────────────────────────────────────────────

def run_batch_convert_only(req: ConvertRequest):
    """Chỉ chạy batch_convert_amass và trả về đường dẫn file amass merge (nếu có)."""
    results_log = []
    log = make_logger(results_log)

    try:
        log("=" * 60)
        log("BƯỚC 1: Batch convert SMPL-X → AMASS .npz (only)")
        log("=" * 60)

        amass_dir = str(DEFAULT_AMASS_DIR)
        os.makedirs(amass_dir, exist_ok=True)

        cmd1, also_merge = build_batch_convert_cmd(req, amass_dir)
        proc1 = run_cmd(cmd1, _HERE, log)

        if proc1.returncode != 0:
            raise RuntimeError(f"batch_convert_amass.py thất bại (code {proc1.returncode})")

        merged_path = None
        if also_merge:
            if req.merge_out:
                merged_path = Path(req.merge_out)
            else:
                merged_path = Path(amass_dir) / "ALL_merged_amass.npz"
            if not merged_path.exists():
                raise RuntimeError(f"Không tìm thấy file merge: {merged_path}")

        return {
            "status": "success",
            "merged_path": str(merged_path) if merged_path else None,
            "log": "\n".join(results_log),
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "log": "\n".join(results_log) + f"\n❌ LỖI: {exc}"
        }


# ─── Merge AMASS npz ──────────────────────────────────────────────────────────

def merge_amass_npz(amass_paths, out_path):
    """Merge multiple AMASS npz by concatenating time-based keys and smoothing the transitions."""
    import numpy as np
    from scipy.signal import savgol_filter

    if not amass_paths:
        raise RuntimeError("No AMASS files to merge.")

    datas = [np.load(p, allow_pickle=True) for p in amass_paths]
    keys = datas[0].files
    merged = {}
    time_keys = {"poses", "trans", "expression"}

    for k in keys:
        arrs = [d[k] for d in datas]
        if k in time_keys:
            concat_arr = np.concatenate(arrs, axis=0)

            if k in ["poses", "trans"] and len(amass_paths) > 1:
                T = concat_arr.shape[0]
                win = min(15, T if T % 2 == 1 else T - 1)
                if win >= 3:
                    concat_arr = savgol_filter(concat_arr, window_length=win, polyorder=3, axis=0)
                    concat_arr = concat_arr.astype(np.float32)

            merged[k] = concat_arr
        else:
            merged[k] = arrs[0]

    np.savez(out_path, **merged)
    return out_path


# ─── Run retarget only ────────────────────────────────────────────────────────

def run_retarget_only(amass_npz: str, output_fbx: str, fps: float, stabilize: bool, rotate_x: float):
    """Chạy Blender retarget — ưu tiên socket server (warm), fallback về subprocess."""
    results_log = []
    log = make_logger(results_log)

    try:
        log("=" * 60)
        log("BƯỚC 2: Blender Retarget (only)")
        log("=" * 60)

        xbot_fbx = str(DEFAULT_XBOT_FBX.resolve())
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)

        log(f"\n  {Path(amass_npz).name} → {Path(output_fbx).name}")

        # ── Thử dùng Blender socket server (warm, nhanh) ──────────────────
        try:
            from .blender_client import send_retarget_cmd, _is_server_alive
            if _is_server_alive():
                log("  [BlenderClient] Gửi lệnh đến Blender socket server...")
                send_retarget_cmd(
                    amass_npz=amass_npz,
                    output_fbx=output_fbx,
                    xbot_fbx=xbot_fbx,
                    fps=fps,
                    stabilize=stabilize,
                    rotate_x=rotate_x,
                )
                log("  ✅ Blender socket server OK")
                return {"status": "success", "log": "\n".join(results_log)}
        except Exception as client_exc:
            log(f"  ⚠ Blender socket server lỗi ({client_exc}) — fallback subprocess")

        # ── Fallback: spawn Blender subprocess ────────────────────────────
        blender_bin = os.environ.get("BLENDER_BIN") or find_blender()
        log(f"  Blender subprocess: {blender_bin}")
        script_retarget = str(_HERE / "blender_retarget_auto.py")

        cmd2 = [
            blender_bin, "--background",
            "--python", script_retarget,
            "--",
            "--amass", amass_npz,
            "--xbot", xbot_fbx,
            "--out", output_fbx,
            "--fps", str(fps),
        ]
        if stabilize:
            cmd2.append("--stabilize")
        if rotate_x != 0.0:
            cmd2 += ["--rotate-x", str(rotate_x)]

        proc2 = run_cmd(cmd2, _HERE, log)
        if proc2.returncode != 0:
            raise RuntimeError(f"Blender retarget thất bại (code {proc2.returncode})")

        return {"status": "success", "log": "\n".join(results_log)}

    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "log": "\n".join(results_log) + f"\n❌ LỖI: {exc}"
        }
