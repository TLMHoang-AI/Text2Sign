#!/usr/bin/env python3
"""
Convert tất cả file trong output_smplerx/ thành AMASS .npz.

Dùng đúng pipeline từ fbx_only_backend/:
  1. load_from_folder  (convert_to_amass.py)
  2. to_amass          (convert_to_amass.py)
  3. batch convert từng folder riêng (batch_convert_amass.py)
  4. merge tất cả thành 1 file lớn  (batch_convert_amass.py)

Output:
  amass_output/
    D0001B_amass.npz
    D0001N_amass.npz
    ...
    ALL_merged_amass.npz

Cách dùng
---------
  python convert_all_to_amass.py
  python convert_all_to_amass.py --root /path/to/output_smplerx
  python convert_all_to_amass.py --out-dir ./my_amass_output
  python convert_all_to_amass.py --fps 30 --zero-legs
  python convert_all_to_amass.py --skip-existing   # chỉ convert folder thiếu
  python convert_all_to_amass.py --no-merge        # không tạo file merge
"""

import os
import re
import sys
import argparse
import numpy as np
from tqdm import tqdm

# ── Import pipeline từ backend ────────────────────────────────────────────────
_BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fbxviewer", "fbx_only_backend")
sys.path.insert(0, _BACKEND)

from convert_to_amass import load_from_folder, to_amass


# ── Constants ─────────────────────────────────────────────────────────────────

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT      = os.path.join(_PROJECT_ROOT, "output_smplerx")
DEFAULT_OUT_DIR   = os.path.join(_BACKEND, "amass_output")
DEFAULT_SMODEL    = os.path.join(_PROJECT_ROOT, "models", "smplx", "SMPLX_NEUTRAL.npz")

# fallback: nếu models/smplx không tồn tại, dùng SMPLX_NEUTRAL.npz cạnh backend
if not os.path.exists(DEFAULT_SMODEL):
    DEFAULT_SMODEL = os.path.join(_BACKEND, "SMPLX_NEUTRAL.npz")


# ── Helpers ───────────────────────────────────────────────────────────────────

def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def resolve_folders(root: str) -> list[tuple[str, str]]:
    """
    Scan root/*/smplx → [(smplx_path, clip_name)].
    clip_name = tên thư mục cha của smplx/.
    """
    folders = []
    for name in sorted(os.listdir(root), key=natural_key):
        smplx_dir = os.path.join(root, name, "smplx")
        if os.path.isdir(smplx_dir):
            folders.append((smplx_dir, name))
    return folders


def trim_idle_frames(seq: dict, threshold: float = 0.05, pad: int = 2) -> dict:
    """
    Cắt frame đứng yên ở đầu/cuối dựa trên frame-to-frame pose change.
    """
    go = seq["global_orient"]
    bp = seq["body_pose"]
    T  = go.shape[0]
    if T < 4:
        return seq

    pose_cat = np.concatenate([go, bp], axis=1)
    diff = np.linalg.norm(pose_cat[1:] - pose_cat[:-1], axis=1)

    active_ids = np.where(diff > threshold)[0]
    if len(active_ids) == 0:
        return {k: v[0:1] for k, v in seq.items()}

    start = max(0, int(active_ids[0]) - pad)
    end   = min(T, int(active_ids[-1]) + 2 + pad)

    return {k: v[start:end] for k, v in seq.items()}


# ── Core conversion ───────────────────────────────────────────────────────────

def convert_folder(smplx_dir: str, clip_name: str, args) -> dict | None:
    """Load → trim (optional) → to_amass → save. Trả về seq dict hoặc None."""
    out_path = os.path.join(args.out_dir, f"{clip_name}{args.suffix}.npz")

    if args.skip_existing and os.path.exists(out_path):
        print(f"  ⏭  Bỏ qua (đã có): {out_path}")
        return None  # vẫn trả về để merge nếu cần

    print(f"\n  [{clip_name}]")
    print(f"    Đang load: {smplx_dir}")

    seq = load_from_folder(smplx_dir)
    T_raw = seq["global_orient"].shape[0]
    print(f"    Frames (raw): {T_raw}")

    if args.trim_idle:
        seq = trim_idle_frames(seq, threshold=args.trim_threshold, pad=args.trim_pad)
        T_trim = seq["global_orient"].shape[0]
        print(f"    Frames (sau trim): {T_trim}  (bỏ {T_raw - T_trim} idle)")
        print(f"    Threshold: {args.trim_threshold} radian, pad: {args.trim_pad}")

    print("    Áp dụng pipeline:")
    if args.zero_legs:
        # zero_legs đã set global_orient=[π,0,0] → skip fix_global_orient
        print("      ✓ zero_legs: global_orient=[π,0,0] + chân T-pose (skip Rx(-90°))")
    else:
        print("      ✓ Rx(-90°) global_orient fix")
    print("      ✓ Thêm hands_mean (SMPL-X)")
    if not args.no_smooth_trans:
        print("      ✓ Savitzky-Golay smooth translation")
    if args.smooth_pose:
        print(f"      ✓ Savitzky-Golay smooth poses (window={args.pose_window})")
    if args.zero_legs:
        print("      ✓ Zero leg joints → T-pose legs")
    if args.zero_trans:
        print("      ✓ Zero translation")
    if args.trim_idle:
        print("      ✓ Trim idle frames (đầu/cuối)")

    amass = to_amass(
        seq,
        fps=args.fps,
        gender=args.gender,
        fix_global_orient=not args.no_fix_orient,
        add_hands_mean=not args.no_hands_mean,
        smooth_trans=not args.no_smooth_trans,
        smooth_poses=args.smooth_pose,
        smooth_poses_window=args.pose_window,
        zero_trans=args.zero_trans,
        zero_legs=args.zero_legs,
        smplx_model_path=args.smplx_model_path,
    )

    os.makedirs(args.out_dir, exist_ok=True)
    np.savez(out_path, **amass)
    print(f"    ✓ Đã lưu: {out_path}")
    print(f"      poses={amass['poses'].shape}  trans={amass['trans'].shape}"
          f"  fps={float(amass['mocap_framerate'])}")

    return seq


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert full output_smplerx/ → AMASS .npz (dùng pipeline backend)"
    )
    parser.add_argument("--root", default=DEFAULT_ROOT,
                        help="Thư mục gốc chứa các clip (default: output_smplerx/)")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                        help="Thư mục output AMASS npz (default: fbxviewer/fbx_only_backend/amass_output/)")
    parser.add_argument("--suffix", default="_amass",
                        help="Suffix cho file output (default: _amass → D0001B_amass.npz)")
    parser.add_argument("--fps", type=float, default=30.0,
                        help="Frame rate (default: 30)")
    parser.add_argument("--gender", default="neutral",
                        choices=["neutral", "male", "female"])

    # Các tùy chọn xử lý (giống batch_convert_amass.py)
    parser.add_argument("--zero-trans", action="store_true",
                        help="Zero out translation — model đứng tại origin")
    parser.add_argument("--no-smooth-trans", action="store_true",
                        help="Không smooth translation bằng Savitzky-Golay")
    parser.add_argument("--no-fix-orient", action="store_true",
                        help="Không áp dụng Rx(-90°) global_orient fix")
    parser.add_argument("--no-hands-mean", action="store_true",
                        help="Không cộng SMPL-X hands_mean vào hand pose")
    parser.add_argument("--smplx-model-path", default=DEFAULT_SMODEL,
                        help=f"Path đến SMPLX_NEUTRAL.npz (default: {DEFAULT_SMODEL})")

    # Smooth pose
    parser.add_argument("--smooth-pose", action="store_true",
                        help="Smooth body_pose bằng Savitzky-Golay (giảm jitter)")
    parser.add_argument("--pose-window", type=int, default=11,
                        help="SavGol window size cho smooth-pose (default: 11; phải lẻ)")

    # Zero legs
    parser.add_argument("--zero-legs", action="store_true",
                        help="Zero out các joint chân → chân giữ T-pose (cho sign language)")

    # Trim idle frames
    parser.add_argument("--trim-idle", action="store_true",
                        help="Cắt bỏ frame đứng yên ở đầu/cuối mỗi clip")
    parser.add_argument("--trim-threshold", type=float, default=0.08,
                        help="Ngưỡng motion cho trim (default: 0.08 radian)")
    parser.add_argument("--trim-pad", type=int, default=2,
                        help="Số frame giữ lại xung quanh vùng có chuyển động (default: 2)")

    # Merge
    parser.add_argument("--no-merge", action="store_true",
                        help="Không tạo file merge tổng hợp tất cả clips")
    parser.add_argument("--merge-out", default=None,
                        help="Tên file merge (default: <out-dir>/ALL_merged_amass.npz)")

    # Utils
    parser.add_argument("--skip-existing", action="store_true",
                        help="Bỏ qua folder đã có file output (tiếp tục merge từ dữ liệu đã load)")
    parser.add_argument("--clips", nargs="+",
                        help="Chỉ xử lý các clip cụ thể, ví dụ: D0001B D0002")

    args = parser.parse_args()

    # ── Validate ────────────────────────────────────────────────────────────
    if not os.path.isdir(args.root):
        print(f"❌ Không tìm thấy thư mục: {args.root}")
        sys.exit(1)

    if not os.path.exists(args.smplx_model_path):
        print(f"❌ Không tìm thấy SMPLX model: {args.smplx_model_path}")
        print(f"   Đặt model tại: models/smplx/SMPLX_NEUTRAL.npz")
        sys.exit(1)

    # ── Resolve folders ──────────────────────────────────────────────────────
    folders = resolve_folders(args.root)
    if not folders:
        print(f"❌ Không tìm thấy folder smplx nào trong: {args.root}")
        sys.exit(1)

    # ── Filter by --clips ───────────────────────────────────────────────────
    if args.clips:
        clip_set = set(args.clips)
        folders = [(d, n) for d, n in folders if n in clip_set]
        print(f"\n  🔍 Lọc clips: {args.clips} → {len(folders)} folder(s) được chọn")

    if not folders:
        print(f"❌ Không có folder nào khớp với clips: {args.clips}")
        sys.exit(1)

    # ── Banner ───────────────────────────────────────────────────────────────
    print(f"""
{'='*65}
  Text2Sign — Full SMPL-X → AMASS Converter
{'='*65}
  Source:    {os.path.abspath(args.root)}
  Output:    {os.path.abspath(args.out_dir)}
  SMPLX:     {os.path.abspath(args.smplx_model_path)}
  FPS:       {args.fps}
  Clips:     {len(folders)}
  Merge:     {'ON → ALL_merged_amass.npz' if not args.no_merge else 'OFF'}
  Zero-trans:{args.zero_trans}
  Zero-legs: {args.zero_legs}
  Trim-idle: {args.trim_idle}
{'='*65}
""")

    # ── Convert từng folder ─────────────────────────────────────────────────
    merge_seqs = []
    succeeded  = []
    skipped    = []
    failed     = []

    for smplx_dir, clip_name in tqdm(folders, desc="Convert clips", unit="clip"):
        out_path = os.path.join(args.out_dir, f"{clip_name}{args.suffix}.npz")

        try:
            seq = convert_folder(smplx_dir, clip_name, args)
            if seq is not None:
                merge_seqs.append(seq)
                succeeded.append(clip_name)
            else:
                skipped.append(clip_name)
                if args.skip_existing:
                    # load lại để đưa vào merge
                    try:
                        seq = load_from_folder(smplx_dir)
                        if args.trim_idle:
                            seq = trim_idle_frames(seq,
                                threshold=args.trim_threshold, pad=args.trim_pad)
                        merge_seqs.append(seq)
                    except Exception:
                        pass
        except Exception as e:
            print(f"\n  ❌ Lỗi [{clip_name}]: {e}")
            failed.append((clip_name, str(e)))

    # ── Merge tất cả ────────────────────────────────────────────────────────
    if not args.no_merge and merge_seqs:
        print(f"\n{'─'*65}")
        print(f"  Merge {len(merge_seqs)} clip(s) → 1 file tổng hợp...")

        KEYS = [
            "global_orient", "body_pose",
            "left_hand_pose", "right_hand_pose",
            "jaw_pose", "leye_pose", "reye_pose",
            "betas", "expression", "transl",
        ]

        merged = {k: np.concatenate([s[k] for s in merge_seqs], axis=0) for k in KEYS}

        # smooth transitions với Savitzky-Golay (giống api/pipeline.merge_amass_npz)
        from scipy.signal import savgol_filter
        T_total = merged["poses"].shape[0]
        if T_total >= 11:
            for k in ["poses", "trans"]:
                win = min(15, T_total if T_total % 2 == 1 else T_total - 1)
                merged[k] = savgol_filter(merged[k], window_length=win,
                                          polyorder=3, axis=0).astype(np.float32)

        amass_merged = to_amass(
            merged,
            fps=args.fps,
            gender=args.gender,
            fix_global_orient=not args.no_fix_orient,
            add_hands_mean=not args.no_hands_mean,
            smooth_trans=not args.no_smooth_trans,
            smooth_poses=args.smooth_pose,
            smooth_poses_window=args.pose_window,
            zero_trans=args.zero_trans,
            zero_legs=args.zero_legs,
            smplx_model_path=args.smplx_model_path,
        )

        merge_out = args.merge_out or os.path.join(args.out_dir, "ALL_merged_amass.npz")
        os.makedirs(args.out_dir, exist_ok=True)
        np.savez(merge_out, **amass_merged)
        print(f"  ✓ Merge đã lưu: {merge_out}")
        print(f"    Total frames: {T_total}  |  poses={amass_merged['poses'].shape}")

    # ── Summary ─────────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  HOÀN THÀNH")
    print(f"  Thành công : {len(succeeded)}/{len(folders)} clips")
    if skipped:
        print(f"  Bỏ qua      : {len(skipped)} clips (đã có)")
    if failed:
        print(f"  Thất bại    : {len(failed)} clips")
        for name, err in failed:
            print(f"    • {name}: {err}")
    print(f"  Output dir  : {os.path.abspath(args.out_dir)}")
    print(f"{'='*65}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
