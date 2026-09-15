#!/usr/bin/env python3
"""
retarget_from_amass.py — Retarget AMASS .npz → X-Bot FBX (dùng pipeline Blender backend).

Dùng khi đã có file AMASS .npz, muốn convert thẳng ra FBX mà không cần chạy lại
từ output_smplerx/.

Cách dùng
---------
  # 1. Từ thư mục chứa AMASS npz (đọc tất cả *_amass.npz)
  python retarget_from_amass.py --amass-dir amass_output --xbot XBOTXBOT.fbx

  # 2. File cụ thể
  python retarget_from_amass.py --amass-file D0001B_amass.npz --xbot XBOTXBOT.fbx

  # 3. Merge nhiều npz thành 1 rồi retarget
  python retarget_from_amass.py --amass-dir amass_output --merge --out merged_xbot.fbx

  # 4. Với tuỳ chọn zero-legs (đọc lại từ output_smplerx → AMASS → FBX luôn)
  #    (dùng batch_convert_amass.py để convert với --zero-legs, rồi chạy script này)

Đầu ra
------
  xbot_retargeted/*.fbx  (hoặc --output-dir tuỳ chỉnh)
"""

import os
import sys
import re
import json
import argparse
import shutil
import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed


# ── Default paths (từ backend) ─────────────────────────────────────────────────

_HERE = Path(__file__).parent.resolve()
_BACKEND = _HERE / "fbxviewer" / "fbx_only_backend"

DEFAULT_XBOT_FBX   = str(_BACKEND / "XBOTXBOT.fbx")
DEFAULT_AMASS_DIR  = str(_BACKEND / "amass_output")
DEFAULT_OUTPUT_DIR = str(_BACKEND / "xbot_retargeted")


# ── Helpers ───────────────────────────────────────────────────────────────────

def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def find_blender(blender_bin_arg: str | None) -> str:
    if blender_bin_arg and blender_bin_arg != "blender":
        if not Path(blender_bin_arg).exists():
            raise FileNotFoundError(f"Blender not found at: {blender_bin_arg}")
        return blender_bin_arg

    candidates = []

    if shutil.which("blender"):
        return "blender"

    import glob
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

    # Thử blender trong thư mục project
    project_blender = _HERE / "blender-4.2.8-linux-x64" / "blender"
    if project_blender.exists():
        return str(project_blender)

    raise FileNotFoundError(
        "Khong tim thay Blender!\n"
        "  • Dat Blender vao PATH, hoac\n"
        "  • Chi dinh --blender-bin, hoac\n"
        "  • Dat Blender tai: Text2Sign/blender-4.2.8-linux-x64/blender"
    )


def merge_amass_npz(amass_paths: list[str], out_path: str):
    """
    Merge nhiều AMASS npz bằng cách nối time-based keys và smooth transition.
    Giống hệt api/pipeline.merge_amass_npz.
    """
    import numpy as np
    from scipy.signal import savgol_filter

    datas = [__import__("numpy").load(p, allow_pickle=True) for p in amass_paths]
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
                    concat_arr = savgol_filter(
                        concat_arr, window_length=win, polyorder=3, axis=0
                    ).astype(np.float32)
            merged[k] = concat_arr
        else:
            merged[k] = arrs[0]

    np.savez(out_path, **merged)
    print(f"  ✓ Merged {len(amass_paths)} files → {out_path}")
    print(f"    Total frames: {merged['poses'].shape[0]}")

    # In thêm frame range info
    frame_start = 1
    fps = float(datas[0]["mocap_framerate"]) if "mocap_framerate" in datas[0].files else 30.0
    duration_s = merged["poses"].shape[0] / fps
    print(f"    Duration: {merged['poses'].shape[0]} frames @ {fps} fps = {duration_s:.1f}s")


def resolve_amass_files(amass_dir: str, clips: list[str] | None) -> list[tuple[str, str]]:
    """
    Tìm tất cả *_amass.npz trong amass_dir.
    Trả về [(clip_name, full_path)].
    """
    if not os.path.isdir(amass_dir):
        raise FileNotFoundError(f"AMASS dir not found: {amass_dir}")

    pairs = []
    for f in sorted(os.listdir(amass_dir), key=natural_key):
        if not f.endswith(".npz"):
            continue
        if f.startswith("ALL_") or "_amass" not in f:
            continue

        clip_name = f.replace("_amass.npz", "").replace("_amass", "")

        # Lọc nếu có --clips
        if clips and clip_name not in clips:
            continue

        pairs.append((clip_name, os.path.join(amass_dir, f)))

    return pairs


def _blender_worker(task: dict) -> tuple[str, int, str]:
    """
    Worker cho ProcessPoolExecutor.
    Trả về (clip_name, returncode, error_msg).
    """
    blender_bin  = task["blender_bin"]
    script       = task["script"]
    amass_npz    = task["amass_npz"]
    output_fbx   = task["output_fbx"]
    xbot_fbx     = task["xbot_fbx"]
    fps          = task["fps"]
    stabilize    = task["stabilize"]
    rotate_x     = task["rotate_x"]

    cmd = [
        blender_bin, "--background",
        "--python", script,
        "--",
        "--amass",  amass_npz,
        "--xbot",   xbot_fbx,
        "--out",    output_fbx,
        "--fps",    str(fps),
    ]
    if stabilize:
        cmd.append("--stabilize")
    if rotate_x != 0.0:
        cmd += ["--rotate-x", str(rotate_x)]

    result = subprocess.run(
        cmd,
        cwd=str(_BACKEND),
        capture_output=True,
        text=True,
    )
    return (
        task["clip_name"],
        result.returncode,
        result.stdout[-2000:] + result.stderr[-2000:],
    )


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Retarget AMASS .npz → X-Bot FBX (Blender headless)"
    )
    parser.add_argument(
        "--amass-dir",
        default=DEFAULT_AMASS_DIR,
        help=f"Thư mục chứa AMASS .npz (default: {DEFAULT_AMASS_DIR})"
    )
    parser.add_argument(
        "--amass-files",
        nargs="+",
        help="Danh sách file .npz cụ thể (thay vì --amass-dir)"
    )
    parser.add_argument(
        "--xbot",
        default=DEFAULT_XBOT_FBX,
        help=f"X-Bot FBX (default: XBOTXBOT.fbx)"
    )
    parser.add_argument(
        "--blender-bin",
        help="Đường dẫn Blender executable (auto-detect nếu không chỉ định)"
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Thư mục chứa FBX output (default: xbot_retargeted/)"
    )
    parser.add_argument(
        "--clips",
        nargs="+",
        help="Chỉ xử lý các clip cụ thể, ví dụ: D0001B W00336B"
    )

    # ── Merge option ────────────────────────────────────────────────────────
    merge_group = parser.add_mutually_exclusive_group()
    merge_group.add_argument(
        "--merge",
        action="store_true",
        help="Merge tất cả *_amass.npz thành 1 file trước khi retarget"
    )
    merge_group.add_argument(
        "--no-merge",
        action="store_true",
        help="Retarget từng file riêng lẻ (default)"
    )

    # ── Retarget options ────────────────────────────────────────────────────
    parser.add_argument(
        "--fps", type=float, default=30.0,
        help="Frame rate (default: 30)"
    )
    parser.add_argument(
        "--no-stabilize", action="store_true",
        help="Cho phép model di chuyển (thay vì giữ tại origin)"
    )
    parser.add_argument(
        "--rotate-x", type=float, default=-90.0,
        help="Góc xoay quanh X (độ). default: -90 (đứng thẳng)"
    )
    parser.add_argument(
        "--parallel", type=int, default=1,
        help="Số tiến trình Blender song song (default: 1)"
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Bỏ qua nếu FBX đã tồn tại"
    )

    args = parser.parse_args()

    # ── Resolve Blender ────────────────────────────────────────────────────
    try:
        blender_bin = find_blender(args.blender_bin)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    xbot_abs = os.path.abspath(args.xbot)
    if not os.path.exists(xbot_abs):
        print(f"❌ Không tìm thấy X-Bot FBX: {xbot_abs}")
        sys.exit(1)

    script_retarget = str(_BACKEND / "blender_retarget_auto.py")
    if not os.path.exists(script_retarget):
        print(f"❌ Không tìm thấy blender_retarget_auto.py: {script_retarget}")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    # ── Resolve AMASS files ─────────────────────────────────────────────────
    if args.amass_files:
        # Dùng danh sách file cụ thể
        if args.merge:
            print("⚠  --merge được bỏ qua khi dùng --amass-files cùng lúc")
        amass_pairs = []
        for fp in args.amass_files:
            fp = os.path.abspath(fp)
            if not fp.endswith("_amass.npz"):
                clip_name = Path(fp).stem
            else:
                clip_name = Path(fp).stem.replace("_amass", "")
            amass_pairs.append((clip_name, fp))
    else:
        amass_pairs = resolve_amass_files(args.amass_dir, args.clips)

    if not amass_pairs:
        print(f"❌ Không tìm thấy file AMASS .npz nào.")
        print(f"   Đường dẫn đã dùng: {args.amass_dir}")
        print(f"   Kiểm tra: --amass-dir hoặc --amass-files")
        sys.exit(1)

    print(f"""
{'='*65}
  Text2Sign — AMASS → X-Bot FBX Retarget
{'='*65}
  Blender    : {blender_bin}
  X-Bot      : {xbot_abs}
  Output dir : {os.path.abspath(args.output_dir)}
  AMASS dir  : {os.path.abspath(args.amass_dir)}
  Clips      : {len(amass_pairs)}
  Merge      : {'ON → 1 file tổng hợp' if args.merge else 'OFF → từng file riêng'}
  Stabilize  : {'ON (giữ origin)' if not args.no_stabilize else 'OFF (cho phép di chuyển)'}
  Rotate X   : {args.rotate_x}°
  Parallel   : {args.parallel}
{'='*65}
""")

    # ── Merge nếu cần ──────────────────────────────────────────────────────
    if args.merge and len(amass_pairs) > 1:
        print(f"\n  Merging {len(amass_pairs)} AMASS npz files...")
        merge_out = os.path.join(args.output_dir, "ALL_merged_xbot.fbx").replace("_xbot.fbx", "_merged_amass.npz")
        merge_amass_npz(
            [p for _, p in amass_pairs],
            merge_out,
        )
        final_pairs = [("ALL_merged", merge_out)]
    else:
        final_pairs = amass_pairs

    # ── Chuẩn bị tasks ─────────────────────────────────────────────────────
    tasks = []
    for clip_name, amass_npz in final_pairs:
        output_fbx = os.path.join(
            args.output_dir,
            f"{clip_name}_xbot.fbx"
        )
        if args.skip_existing and os.path.exists(output_fbx):
            print(f"  ⏭  Bỏ qua (đã có): {output_fbx}")
            continue
        tasks.append({
            "clip_name":  clip_name,
            "amass_npz":  amass_npz,
            "output_fbx": output_fbx,
            "xbot_fbx":   xbot_abs,
            "blender_bin": blender_bin,
            "script":      script_retarget,
            "fps":         args.fps,
            "stabilize":   not args.no_stabilize,
            "rotate_x":    args.rotate_x,
        })

    if not tasks:
        print("\n✅ Không cần làm gì — tất cả FBX đã tồn tại (--skip-existing).")
        sys.exit(0)

    # ── Chạy Blender ───────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  Blender Retarget: {len(tasks)} clip(s)")
    print(f"{'='*65}\n")

    succeeded, failed = [], []

    if args.parallel > 1:
        with ProcessPoolExecutor(max_workers=args.parallel) as executor:
            futures = {executor.submit(_blender_worker, t): t["clip_name"] for t in tasks}
            for future in as_completed(futures):
                clip_name = futures[future]
                try:
                    name, code, err = future.result()
                    if code == 0:
                        succeeded.append(name)
                        print(f"  ✅ {name}")
                    else:
                        failed.append((name, err[-500:]))
                        print(f"  ❌ {name} (returncode={code})")
                        print(f"     {err[-300:]}")
                except Exception as e:
                    failed.append((clip_name, str(e)))
                    print(f"  ❌ {clip_name}: {e}")
    else:
        for task in tasks:
            name, code, err = _blender_worker(task)
            if code == 0:
                succeeded.append(name)
                print(f"  ✅ {name}")
            else:
                failed.append((name, err[-500:]))
                print(f"  ❌ {name} (returncode={code})")
                print(f"     {err[-300:]}")

    # ── Tổng kết ───────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  HOÀN THÀNH")
    print(f"  Thành công : {len(succeeded)}/{len(tasks)} clips")
    if failed:
        print(f"  Thất bại   : {len(failed)} clips")
        for n, err in failed:
            print(f"    • {n}")
    print(f"  Output dir : {os.path.abspath(args.output_dir)}")
    print(f"{'='*65}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
