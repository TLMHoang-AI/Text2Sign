#!/usr/bin/env python3
"""
automation.py — Tự động hoá pipeline đầu-cuối:
  output_smplerx  →  batch_convert_amass  →  Blender retarget  →  FBX output

Các bước:
  1. Dùng batch_convert_amass.py để convert các folder output_smplerx/*/smplx
     thành các file amass .npz riêng lẻ.
  2. Với từng file amass .npz, gọi Blender headless để chạy blender_retarget_auto.py
     và output ra FBX đã retarget sang X-Bot.

Cách dùng
----------
# Scan toàn bộ output_smplerx, dùng XBOTXBOT.fbx mặc định:
  python automation.py

# Chỉ một số folder cụ thể:
  python automation.py --folders output_smplerx/D0001B/smplx output_smplerx/D0002/smplx

# Chỉ định model X-Bot khác:
  python automation.py --xbot XBot(1).fbx

# Chỉ chạy bước 1 (convert amass), bỏ qua Blender:
  python automation.py --no-blender

# Chỉ chạy bước 2 (Blender) từ file amass đã có sẵn:
  python automation.py --no-convert --amass-dir amass_output/


# Parallel mode (chạy nhiều Blender cùng lúc):
  python automation.py --parallel 4
"""

import os
import sys
import re
import argparse
import subprocess
import shutil
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

# ─── Default Paths ───────────────────────────────────────────────────────────
_HERE = Path(__file__).parent.resolve()

DEFAULT_ROOT        = str(_HERE / "output_smplerx")
DEFAULT_XBOT_FBX    = str(_HERE / "XBOTXBOT.fbx")
DEFAULT_AMASS_DIR   = str(_HERE / "amass_output")
DEFAULT_OUTPUT_DIR  = str(_HERE / "xbot_retargeted")
DEFAULT_BLENDER_BIN = "blender"

# ─── Helpers ─────────────────────────────────────────────────────────────────

def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def find_blender() -> str:
    """Tìm blender executable trên Linux và Windows."""
    # 1. Đã có trong PATH
    if shutil.which("blender"):
        return "blender"

    if sys.platform == "win32":
        # Windows: scan Program Files
        candidates = []
        for base in [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        ]:
            bf_dir = os.path.join(base, "Blender Foundation")
            if os.path.isdir(bf_dir):
                # Scan tất cả sub-folder (Blender 4.x, Blender 3.x, ...)
                for entry in sorted(os.listdir(bf_dir), reverse=True):
                    exe = os.path.join(bf_dir, entry, "blender.exe")
                    if os.path.isfile(exe):
                        candidates.append(exe)
            # Fallback cố định
            for ver in ["4.3", "4.2", "4.1", "4.0", "3.6", "3.5", "3.4", "3.3"]:
                exe = os.path.join(base, "Blender Foundation", f"Blender {ver}", "blender.exe")
                candidates.append(exe)
        for exe in candidates:
            if os.path.isfile(exe):
                return exe
    else:
        # Linux / macOS
        linux_paths = [
            "/usr/bin/blender",
            "/usr/local/bin/blender",
            "/snap/bin/blender",
            os.path.expanduser("~/blender/blender"),
            os.path.expanduser("~/blender-*/blender"),
            "/opt/blender/blender",
        ]
        import glob
        for p in linux_paths:
            # hỗ trợ glob pattern (e.g. ~/blender-*/blender)
            matches = glob.glob(p)
            for m in (matches if matches else [p]):
                if os.path.isfile(m) and os.access(m, os.X_OK):
                    return m

    raise FileNotFoundError(
        "❌ Không tìm thấy Blender! Hãy cài Blender hoặc chỉ định --blender-bin.\n"
        "   Ví dụ: python automation.py --blender-bin \"C:\\\\Program Files\\\\Blender Foundation\\\\Blender 4.2\\\\blender.exe\""
    )


def run_batch_convert(
    root: str | None,
    folders: list[str] | None,
    amass_dir: str,
    fps: float,
    gender: str,
    zero_trans: bool,
    no_smooth_trans: bool,
    no_fix_orient: bool,
    no_hands_mean: bool,
    smplx_model_path: str,
    also_merge: bool,
    skip_existing: bool,
    trim_idle: bool,
    trim_threshold: float,
    trim_pad: int,
    smooth_pose: bool,
    pose_window: int,
    zero_legs: bool,
) -> list[tuple[str, str]]:
    """
    Chạy batch_convert_amass.py.
    Trả về list of (clip_name, amass_npz_path).
    """
    script = str(_HERE / "batch_convert_amass.py")
    cmd = [sys.executable, script]

    if folders:
        cmd += ["--folders"] + folders
    else:
        cmd += ["--root", root]

    cmd += ["--out-dir", amass_dir]
    cmd += ["--fps", str(fps)]
    cmd += ["--gender", gender]
    cmd += ["--smplx-model-path", smplx_model_path]

    if zero_trans:
        cmd.append("--zero-trans")
    if no_smooth_trans:
        cmd.append("--no-smooth-trans")
    if no_fix_orient:
        cmd.append("--no-fix-orient")
    if no_hands_mean:
        cmd.append("--no-hands-mean")
    if also_merge:
        cmd.append("--also-merge")
    if skip_existing:
        cmd.append("--skip-existing")
    if trim_idle:
        cmd.append("--trim-idle")
        cmd += ["--trim-threshold", str(trim_threshold)]
        cmd += ["--trim-pad", str(trim_pad)]
    if smooth_pose:
        cmd.append("--smooth-pose")
        cmd += ["--pose-window", str(pose_window)]
    if zero_legs:
        cmd.append("--zero-legs")

    print("\n" + "="*60)
    print("📦 BƯỚC 1: Batch convert SMPL-X → AMASS .npz")
    print("="*60)
    print(f"  Command: {' '.join(cmd)}\n")

    ret = subprocess.run(cmd, cwd=str(_HERE))
    if ret.returncode != 0:
        raise RuntimeError(f"batch_convert_amass.py thất bại (code {ret.returncode})")

    # Detect output files
    out_path = Path(amass_dir)
    if also_merge:
        # Nhiều folder → chỉ retarget file merged, không chạy riêng từng clip
        merged_file = out_path / "ALL_merged_amass.npz"
        if not merged_file.exists():
            raise RuntimeError(f"❌ Không tìm thấy file merge: {merged_file}")
        print(f"  🔗 Chế độ multi-folder: chỉ retarget file merged → {merged_file.name}")
        return [("ALL_merged", str(merged_file))]
    else:
        # 1 folder → retarget riêng lẻ
        results = []
        for f in sorted(out_path.glob("*_amass.npz"), key=lambda p: natural_key(p.name)):
            if f.name.startswith("ALL_"):
                continue
            clip_name = f.stem.replace("_amass", "")
            results.append((clip_name, str(f)))
        return results



def run_blender_retarget(
    amass_npz: str,
    xbot_fbx: str,
    output_fbx: str,
    fps: float,
    blender_bin: str,
    stabilize: bool,
    rotate_x: float,
) -> int:
    """
    Gọi Blender headless để retarget 1 file amass .npz → FBX.
    Trả về returncode.
    """
    script = str(_HERE / "blender_retarget_auto.py")

    cmd = [
        blender_bin,
        "--background",
        "--python", script,
        "--",
        "--amass", amass_npz,
        "--xbot", xbot_fbx,
        "--out", output_fbx,
        "--fps", str(fps),
    ]

    if stabilize:
        cmd.append("--stabilize")
    if rotate_x != 0.0:
        cmd += ["--rotate-x", str(rotate_x)]

    print(f"\n  🎬 Blender: {Path(amass_npz).name} → {Path(output_fbx).name}")
    print(f"     CMD: {' '.join(cmd)}")

    ret = subprocess.run(cmd, cwd=str(_HERE))
    return ret.returncode


def _worker(args_tuple):
    """Worker function cho ProcessPoolExecutor."""
    (clip_name, amass_npz, xbot_fbx, output_fbx,
     fps, blender_bin, stabilize, rotate_x) = args_tuple
    code = run_blender_retarget(
        amass_npz, xbot_fbx, output_fbx, fps,
        blender_bin, stabilize, rotate_x
    )
    return clip_name, code


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _should_merge(args) -> bool:
    """
    Tự động bật also_merge khi xử lý nhiều hơn 1 folder.
    Có thể tắt bằng --no-merge.
    """
    if getattr(args, "no_merge", False):
        return False
    # --folders mode: merge nếu có > 1 folder
    if args.folders and len(args.folders) > 1:
        return True
    # --root mode: luôn merge vì scan nhiều folder
    if not args.folders:
        return True
    return False


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Automation pipeline: output_smplerx → amass → Blender retarget → FBX",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── Nguồn đầu vào ──────────────────────────────────────────────────────
    src_group = parser.add_mutually_exclusive_group()
    src_group.add_argument(
        "--root", default=DEFAULT_ROOT,
        help=f"Scan tất cả subfolder */smplx trong root (default: {DEFAULT_ROOT})"
    )
    src_group.add_argument(
        "--folders", nargs="+",
        help="Danh sách thư mục smplx cụ thể, ví dụ: output_smplerx/D0001B/smplx ..."
    )

    # ── Blender / X-Bot ────────────────────────────────────────────────────
    parser.add_argument("--xbot",  default=DEFAULT_XBOT_FBX,
                        help=f"Đường dẫn X-Bot FBX (default: XBOTXBOT.fbx)")
    parser.add_argument("--blender-bin", default=DEFAULT_BLENDER_BIN,
                        help="Blender executable (default: blender)")

    # ── Output ─────────────────────────────────────────────────────────────
    parser.add_argument("--amass-dir", default=DEFAULT_AMASS_DIR,
                        help=f"Thư mục chứa AMASS .npz trung gian (default: amass_output/)")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help=f"Thư mục chứa FBX output (default: xbot_retargeted/)")

    # ── Pipeline control ───────────────────────────────────────────────────
    parser.add_argument("--no-convert", action="store_true",
                        help="Bỏ qua bước 1 (batch_convert_amass), dùng amass-dir đã có")
    parser.add_argument("--no-blender", action="store_true",
                        help="Bỏ qua bước 2 (Blender retarget), chỉ convert amass")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Bỏ qua nếu file output FBX đã tồn tại")
    parser.add_argument("--parallel", type=int, default=1,
                        help="Số tiến trình Blender chạy song song (default: 1)")

    # ── batch_convert options ──────────────────────────────────────────────
    parser.add_argument("--fps", type=float, default=30.0, help="Frame rate (default: 30)")
    parser.add_argument("--gender", default="neutral", choices=["neutral", "male", "female"])
    parser.add_argument("--zero-trans", action="store_true",
                        help="Zero out translation (model stays at origin)")
    parser.add_argument("--no-smooth-trans", action="store_true")
    parser.add_argument("--no-fix-orient", action="store_true")
    parser.add_argument("--no-hands-mean", action="store_true")
    parser.add_argument("--smplx-model-path", default="models/smplx/SMPLX_NEUTRAL.npz")
    parser.add_argument("--no-merge", action="store_true",
                        help="Không tạo file merge khi có nhiều folder")
    parser.add_argument("--smooth-pose", action="store_true",
                        help="Smooth joint rotations (body_pose) để giảm jitter. Default: tắt")
    parser.add_argument("--pose-window", type=int, default=7,
                        help="SavGol window size cho smooth-pose (default: 7)")
    parser.add_argument("--zero-legs", action="store_true",
                        help="Zero out joint chân → chân giữ T-pose, không cử động")
    # ── Trim idle frames ──────────────────────────────────────────────────────
    parser.add_argument("--no-trim", action="store_false", dest="trim_idle",
                        help="Tắt trim idle frames (mặc định: bật)")
    parser.set_defaults(trim_idle=True)
    parser.add_argument("--trim-threshold", type=float, default=0.08,
                        help="Ngưỡng motion (radian) để detect frame đứng yên (default: 0.08)")
    parser.add_argument("--trim-pad", type=int, default=2,
                        help="Số frame buffer giữ xung quanh vùng có chuyển động (default: 2)")

    # ── Blender retarget options ───────────────────────────────────────────
    parser.add_argument("--no-stabilize", action="store_false", dest="stabilize",
                        help="Không giữ model tại origin. Mặc định: stabilize=True")
    parser.set_defaults(stabilize=True)
    parser.add_argument("--rotate-x", type=float, default=-90.0,
                        help="Rotate model quanh trục X (độ). Default: -90")

    # ── Lọc clip ───────────────────────────────────────────────────────────
    parser.add_argument("--clips", nargs="+",
                        help="Chỉ xử lý các clip cụ thể, ví dụ: D0001B D0002")

    args = parser.parse_args()

    print("\n" + "="*60)
    print("🤖 Text2Sign Automation Pipeline")
    print("="*60)
    print(f"  X-Bot FBX   : {args.xbot}")
    print(f"  AMASS dir   : {args.amass_dir}")
    print(f"  Output dir  : {args.output_dir}")
    print(f"  Rotate X    : {args.rotate_x}° (mặc định -90)")
    print(f"  Parallel    : {args.parallel}")

    # ── Bước 1: Batch Convert ────────────────────────────────────────────
    if not args.no_convert:
        amass_pairs = run_batch_convert(
            root=args.root if not args.folders else None,
            folders=args.folders,
            amass_dir=args.amass_dir,
            fps=args.fps,
            gender=args.gender,
            zero_trans=args.zero_trans,
            no_smooth_trans=args.no_smooth_trans,
            no_fix_orient=args.no_fix_orient,
            no_hands_mean=args.no_hands_mean,
            smplx_model_path=args.smplx_model_path,
            also_merge=_should_merge(args),
            skip_existing=args.skip_existing,
            trim_idle=args.trim_idle,
            trim_threshold=args.trim_threshold,
            trim_pad=args.trim_pad,
            smooth_pose=args.smooth_pose,
            pose_window=args.pose_window,
            zero_legs=args.zero_legs,
        )
    else:
        # Dùng amass_dir đã có
        amass_pairs = []
        for f in sorted(Path(args.amass_dir).glob("*_amass.npz"),
                        key=lambda p: natural_key(p.name)):
            clip_name = f.stem.replace("_amass", "")
            amass_pairs.append((clip_name, str(f)))
        print(f"\n⏩ Bỏ qua bước convert. Tìm thấy {len(amass_pairs)} file amass.npz trong {args.amass_dir}")

    # ── Lọc clip nếu có --clips ──────────────────────────────────────────
    if args.clips:
        clip_set = set(args.clips)
        amass_pairs = [(n, p) for (n, p) in amass_pairs if n in clip_set]
        print(f"\n🔍 Lọc clips: {args.clips} → {len(amass_pairs)} clip(s) được chọn")

    if not amass_pairs:
        print("❌ Không có file amass .npz nào để xử lý. Kiểm tra lại --root / --amass-dir.")
        sys.exit(1)

    # ── Bước 2: Blender Retarget ─────────────────────────────────────────
    if args.no_blender:
        print(f"\n⏩ Bỏ qua bước Blender (--no-blender). Xong!")
        sys.exit(0)

    # Tìm blender
    try:
        blender_bin = find_blender() if args.blender_bin == DEFAULT_BLENDER_BIN else args.blender_bin
    except FileNotFoundError as e:
        print(str(e))
        sys.exit(1)

    print(f"  Blender     : {blender_bin}")

    # Tạo thư mục output
    os.makedirs(args.output_dir, exist_ok=True)

    # Chuẩn bị danh sách task
    tasks = []
    for clip_name, amass_npz in amass_pairs:
        output_fbx = str(Path(args.output_dir) / f"{clip_name}_xbot.fbx")
        if args.skip_existing and Path(output_fbx).exists():
            print(f"  ⏭ Bỏ qua (đã có): {output_fbx}")
            continue
        tasks.append((
            clip_name, amass_npz,
            str(Path(args.xbot).resolve()),
            str(Path(output_fbx).resolve()),
            args.fps, blender_bin,
            args.stabilize, args.rotate_x,
        ))

    if not tasks:
        print("✅ Tất cả FBX đã tồn tại (--skip-existing). Không cần làm gì thêm.")
        sys.exit(0)

    print(f"\n{'='*60}")
    print(f"🎬 BƯỚC 2: Blender Retarget ({len(tasks)} clip(s))")
    print(f"{'='*60}")

    succeeded, failed = [], []

    if args.parallel > 1:
        with ProcessPoolExecutor(max_workers=args.parallel) as executor:
            futures = {executor.submit(_worker, t): t[0] for t in tasks}
            for future in as_completed(futures):
                clip_name = futures[future]
                try:
                    name, code = future.result()
                    if code == 0:
                        succeeded.append(name)
                        print(f"  ✅ {name}")
                    else:
                        failed.append((name, f"returncode={code}"))
                        print(f"  ❌ {name} (returncode={code})")
                except Exception as e:
                    failed.append((clip_name, str(e)))
                    print(f"  ❌ {clip_name}: {e}")
    else:
        for task in tasks:
            clip_name, amass_npz, xbot_fbx, output_fbx, \
                fps, blender_bin, stabilize, rotate_x = task
            code = run_blender_retarget(
                amass_npz, xbot_fbx, output_fbx, fps,
                blender_bin, stabilize, rotate_x
            )
            if code == 0:
                succeeded.append(clip_name)
                print(f"  ✅ {clip_name}")
            else:
                failed.append((clip_name, f"returncode={code}"))
                print(f"  ❌ {clip_name} (returncode={code})")

    # ── Tổng kết ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"📊 Tổng kết")
    print(f"{'='*60}")
    print(f"  ✅ Thành công : {len(succeeded)}/{len(tasks)}")
    if failed:
        print(f"  ❌ Thất bại  : {len(failed)}")
        for name, err in failed:
            print(f"     - {name}: {err}")
    print(f"  📂 Output dir : {Path(args.output_dir).resolve()}")


if __name__ == "__main__":
    main()
