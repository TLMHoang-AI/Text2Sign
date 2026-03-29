"""
api/helpers.py — Các hàm tiện ích dùng chung trong pipeline FBX.
"""

import os
import sys
import re
import csv
import glob
import subprocess
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from .config import (
    _HERE,
    _PROJECT_ROOT,
    DEFAULT_ROOT,
    DEFAULT_XBOT_FBX,
    DEFAULT_AMASS_DIR,
    DEFAULT_OUTPUT_DIR,
    natural_key,
)

if TYPE_CHECKING:
    from .models import ConvertRequest


# ─── Dictionary ───────────────────────────────────────────────────────────────

def load_dictionary_mapping():
    csv_path = _PROJECT_ROOT / "dictionary_data.csv"
    if not csv_path.exists():
        return {}
    mapping = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            image_id = row.get("image_id", "").strip()
            text = row.get("text", "").strip()
            if image_id and text:
                mapping[image_id] = text
    return mapping


# ─── Text ─────────────────────────────────────────────────────────────────────

def split_sentences(text: str):
    """Split a paragraph into sentences using simple punctuation/newline rules."""
    if not text:
        return []
    cleaned = text.strip()
    if not cleaned:
        return []
    cleaned = (
        cleaned
        .replace("。", ".")
        .replace("！", "!")
        .replace("？", "?")
    )
    parts = re.split(r"(?<=[.!?])\s+|\n+|;+", cleaned)
    sentences = [p.strip() for p in parts if p.strip()]
    return sentences


# ─── Blender ──────────────────────────────────────────────────────────────────

def find_blender() -> str:
    """Tìm blender executable trên Linux và Windows."""
    if shutil.which("blender"):
        return "blender"

    if sys.platform == "win32":
        candidates = []
        for base in [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        ]:
            bf_dir = os.path.join(base, "Blender Foundation")
            if os.path.isdir(bf_dir):
                for entry in sorted(os.listdir(bf_dir), reverse=True):
                    exe = os.path.join(bf_dir, entry, "blender.exe")
                    if os.path.isfile(exe):
                        candidates.append(exe)
            for ver in ["4.3", "4.2", "4.1", "4.0", "3.6", "3.5", "3.4", "3.3"]:
                exe = os.path.join(base, "Blender Foundation", f"Blender {ver}", "blender.exe")
                candidates.append(exe)
        for exe in candidates:
            if os.path.isfile(exe):
                return exe
    else:
        linux_paths = [
            "/usr/bin/blender",
            "/usr/local/bin/blender",
            "/snap/bin/blender",
            os.path.expanduser("~/blender/blender"),
            os.path.expanduser("~/blender-*/blender"),
            "/opt/blender/blender",
        ]
        for p in linux_paths:
            matches = glob.glob(p)
            for m in (matches if matches else [p]):
                if os.path.isfile(m) and os.access(m, os.X_OK):
                    return m

    raise FileNotFoundError(
        "Không tìm thấy Blender. \n"
        "Nếu dùng Docker: Hãy mount folder Blender từ host vào container và dùng path tương ứng. \n"
        "Nếu dùng local: Hãy thêm Bliss/Blender vào PATH hoặc set biến môi trường BLENDER_BIN."
    )


# ─── Logging ──────────────────────────────────────────────────────────────────

def make_logger(results_log):
    def log(line: str):
        results_log.append(line)
        print(line, flush=True)
    return log


# ─── Pipeline Helpers ─────────────────────────────────────────────────────────

def resolve_folders(folders):
    abs_folders = []
    for f in folders:
        p = DEFAULT_ROOT / f / "smplx"
        if not p.exists():
            p2 = DEFAULT_ROOT / f
            p = p2 if p2.exists() else p
        abs_folders.append(str(p))
    return abs_folders


def build_batch_convert_cmd(req: "ConvertRequest", amass_dir: str):
    cmd = [sys.executable, str(_HERE / "batch_convert_amass.py")]
    if req.folders:
        abs_folders = resolve_folders(req.folders)
        cmd += ["--folders"] + abs_folders
        also_merge = (len(req.folders) > 1) and not req.no_merge
    else:
        cmd += ["--root", str(DEFAULT_ROOT)]
        also_merge = not req.no_merge

    cmd += [
        "--out-dir", amass_dir,
        "--fps", str(req.fps),
        "--gender", req.gender,
        "--smplx-model-path", req.smplx_model_path,
    ]
    if req.zero_trans:        cmd.append("--zero-trans")
    if req.no_smooth_trans:   cmd.append("--no-smooth-trans")
    if req.no_fix_orient:     cmd.append("--no-fix-orient")
    if req.no_hands_mean:     cmd.append("--no-hands-mean")
    if also_merge:            cmd.append("--also-merge")
    if req.skip_existing:     cmd.append("--skip-existing")
    if req.trim_idle:
        cmd += ["--trim-idle", "--trim-threshold", str(req.trim_threshold),
                "--trim-pad", str(req.trim_pad)]
    if req.smooth_pose:
        cmd += ["--smooth-pose", "--pose-window", str(req.pose_window)]
    if req.zero_legs:         cmd.append("--zero-legs")
    if req.merge_out:
        cmd += ["--merge-out", str(req.merge_out)]

    return cmd, also_merge


def collect_amass_pairs(req: "ConvertRequest", amass_dir: str, also_merge: bool):
    amass_out = Path(amass_dir)
    if also_merge:
        if req.merge_out:
            merged = Path(req.merge_out)
        else:
            merged = amass_out / "ALL_merged_amass.npz"
        if not merged.exists():
            raise RuntimeError(f"Không tìm thấy file merge: {merged}")
        clip_name = merged.stem.replace("_amass", "")
        return [(clip_name, str(merged))]

    amass_pairs = []
    for f in sorted(amass_out.glob("*_amass.npz"), key=lambda p: natural_key(p.name)):
        if f.name.startswith("ALL_"):
            continue
        clip_name = f.stem.replace("_amass", "")
        amass_pairs.append((clip_name, str(f)))
    return amass_pairs


def run_cmd(cmd, cwd, log):
    log(f"CMD: {' '.join(cmd)}\n")
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if proc.stdout:
        log("[STDOUT]\n" + proc.stdout)
    if proc.stderr:
        log("[STDERR]\n" + proc.stderr)
    return proc


def build_blender_batch_payload(amass_pairs, output_dir, req: "ConvertRequest", xbot_fbx):
    batch_items = []
    for clip_name, amass_npz in amass_pairs:
        output_fbx = str(Path(output_dir) / f"{clip_name}_xbot.fbx")
        if req.skip_existing and Path(output_fbx).exists():
            batch_items.append(
                {
                    "clip": clip_name,
                    "amass": amass_npz,
                    "out": output_fbx,
                    "fps": req.fps,
                    "skip": True,
                }
            )
            continue
        batch_items.append(
            {
                "clip": clip_name,
                "amass": amass_npz,
                "out": output_fbx,
                "fps": req.fps,
            }
        )
    payload = {"xbot": xbot_fbx, "fps": req.fps, "items": batch_items}
    return payload, batch_items
