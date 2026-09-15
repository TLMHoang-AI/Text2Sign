#!/usr/bin/env python3
"""
Batch convert nhiều folder smplx per-frame .npz → mỗi folder ra 1 file amass.npz riêng.

Cấu trúc đầu vào:
  output_smplerx/
    D0001B/smplx/*.npz   (per-frame)
    D0002/smplx/*.npz
    ...

Output (--out-dir amass_output/):
  amass_output/
    D0001B_amass.npz
    D0002_amass.npz
    ALL_merged_amass.npz  (nếu --also-merge)

Cách dùng
---------
  python batch_convert_amass.py --root output_smplerx --out-dir amass_output/
  python batch_convert_amass.py --folders output_smplerx/D0001B/smplx output_smplerx/D0002/smplx --out-dir amass_output/
  python batch_convert_amass.py --root output_smplerx --out-dir amass_output/ --also-merge
"""

import os
import re
import sys
import argparse
import numpy as np
from tqdm import tqdm

# ── Import to_amass từ convert_to_amass.py cùng thư mục ─────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from convert_to_amass import load_from_folder, to_amass


def trim_idle_frames(seq: dict, threshold: float = 0.05, pad: int = 2) -> dict:
    """
    Cắt bỏ các frame đứng yên (ít cử động) ở đầu và cuối mỗi clip.

    Phương pháp: frame-to-frame change của (global_orient + body_pose).
    Frame được coi là "đứng yên" nếu norm thay đổi < threshold.

    threshold : ngưỡng motion (radian). ~0.03 = rất nhạy, 0.10 = ít nhạy
    pad       : số frame giữ lại trước/sau vùng có chuyển động
    """
    go = seq["global_orient"]   # (T, 3)
    bp = seq["body_pose"]       # (T, 63)
    T  = go.shape[0]
    if T < 4:
        return seq

    pose_cat = np.concatenate([go, bp], axis=1)               # (T, 66)
    diff = np.linalg.norm(pose_cat[1:] - pose_cat[:-1], axis=1)  # (T-1,)

    active_ids = np.where(diff > threshold)[0]
    if len(active_ids) == 0:
        return {k: v[0:1] for k, v in seq.items()}  # toàn bộ đứng yên

    # diff[i] = change from frame i → frame i+1
    start = max(0, int(active_ids[0]) - pad)
    end   = min(T, int(active_ids[-1]) + 2 + pad)  # +2: include frame sau last change

    return {k: v[start:end] for k, v in seq.items()}


def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def resolve_folders(args) -> list[tuple[str, str]]:
    """
    Trả về list of (folder_path, clip_name).
    clip_name dựa trên tên thư mục cha của smplx/ (e.g., D0001B).
    """
    folders = []

    if args.folders:
        for folder in args.folders:
            folder = folder.rstrip("/")
            parent = os.path.dirname(folder)
            clip_name = os.path.basename(parent) if os.path.basename(folder) == "smplx" else os.path.basename(folder)
            folders.append((folder, clip_name))
    else:  # --root mode
        root = args.root.rstrip("/")
        for name in sorted(os.listdir(root), key=natural_key):
            smplx_dir = os.path.join(root, name, "smplx")
            if os.path.isdir(smplx_dir):
                folders.append((smplx_dir, name))

    return folders


def main():
    parser = argparse.ArgumentParser(
        description="Batch convert mỗi folder smplx per-frame .npz → file amass.npz riêng"
    )

    src_group = parser.add_mutually_exclusive_group(required=True)
    src_group.add_argument(
        "--root",
        help="Tự động scan tất cả subfolder */smplx trong root. VD: output_smplerx"
    )
    src_group.add_argument(
        "--folders", nargs="+",
        help="Danh sách các folder smplx cụ thể. VD: output_smplerx/D0001B/smplx ..."
    )

    parser.add_argument("--out-dir", default="amass_output",
                        help="Thư mục chứa các file amass.npz output (default: amass_output)")
    parser.add_argument("--suffix", default="_amass",
                        help="Suffix tên file output (default: _amass → D0001B_amass.npz)")
    parser.add_argument("--fps", type=float, default=30.0,
                        help="Frame rate (default: 30)")
    parser.add_argument("--gender", default="neutral",
                        choices=["neutral", "male", "female"])
    parser.add_argument("--zero-trans", action="store_true",
                        help="Zero out translation (model stays at origin)")
    parser.add_argument("--no-smooth-trans", action="store_true",
                        help="Không smooth translation bằng Savitzky-Golay")
    parser.add_argument("--smooth-pose", action="store_true",
                        help="Smooth body_pose bằng Savitzky-Golay để giảm jitter")
    parser.add_argument("--pose-window", type=int, default=11,
                        help="SavGol window size cho smooth-pose (default: 11; 15-21 mượt hơn, phải lẻ)")
    parser.add_argument("--zero-legs", action="store_true",
                        help="Zero out các joint chân (Hip/Knee/Ankle/Foot) → chân giữ T-pose")
    parser.add_argument("--no-fix-orient", action="store_true",
                        help="Không áp dụng Rx(-90°) global_orient fix")
    parser.add_argument("--no-hands-mean", action="store_true",
                        help="Không cộng SMPL-X hands_mean vào hand pose")
    parser.add_argument("--smplx-model-path", default="models/smplx/SMPLX_NEUTRAL.npz",
                        help="Đường dẫn SMPLX_NEUTRAL.npz (default: models/smplx/SMPLX_NEUTRAL.npz)")
    parser.add_argument("--also-merge", action="store_true",
                        help="Ngoài các file riêng lẻ, tạo thêm 1 file merge tất cả (ALL_merged_amass.npz)")
    parser.add_argument("--merge-out", default=None,
                        help="Tên file merge output (default: <out-dir>/ALL_merged_amass.npz)")
    parser.add_argument("--trim-idle", action="store_true",
                        help="Cắt bỏ frame đứng yên ở đầu/cuối mỗi clip trước khi merge")
    parser.add_argument("--trim-threshold", type=float, default=0.08,
                        help="Ngưỡng motion để xác định frame đứng yên (default: 0.08 radian)")
    parser.add_argument("--trim-pad", type=int, default=2,
                        help="Số frame giữ lại xung quanh vùng có chuyển động (default: 2)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Bỏ qua nếu file output đã tồn tại")
    args = parser.parse_args()

    # ── Xác định danh sách folder ────────────────────────────────────────────
    folders = resolve_folders(args)
    if not folders:
        print("❌ Không tìm thấy folder smplx nào!")
        sys.exit(1)

    # ── Tạo thư mục output ───────────────────────────────────────────────────
    os.makedirs(args.out_dir, exist_ok=True)

    print(f"\nTìm thấy {len(folders)} folder(s) để convert:")
    for i, (folder, name) in enumerate(folders, 1):
        out_path = os.path.join(args.out_dir, f"{name}{args.suffix}.npz")
        status = "⏭ (exists)" if (args.skip_existing and os.path.exists(out_path)) else ""
        print(f"  [{i:3d}] {name:20s}  →  {out_path} {status}")

    print()

    # ── Convert từng folder ──────────────────────────────────────────────────
    merge_seqs = []  # accumulate nếu --also-merge
    KEYS = ["global_orient", "body_pose", "left_hand_pose", "right_hand_pose",
            "jaw_pose", "leye_pose", "reye_pose", "betas", "expression", "transl"]

    failed = []
    succeeded = []

    for folder, clip_name in folders:
        out_path = os.path.join(args.out_dir, f"{clip_name}{args.suffix}.npz")

        if args.skip_existing and os.path.exists(out_path):
            print(f"  ⏭ Bỏ qua (đã có): {out_path}")
            # vẫn load để merge nếu cần
            if args.also_merge:
                try:
                    seq = load_from_folder(folder)
                    if args.trim_idle:
                        seq = trim_idle_frames(seq, threshold=args.trim_threshold, pad=args.trim_pad)
                    merge_seqs.append(seq)
                except Exception:
                    pass
            continue

        print(f"\n{'─'*60}")
        print(f"Đang xử lý: {folder}  [{clip_name}]")

        try:
            seq = load_from_folder(folder)
            T_raw = seq["global_orient"].shape[0]
            print(f"   Tổng frames (raw): {T_raw}")

            if args.trim_idle:
                seq = trim_idle_frames(seq, threshold=args.trim_threshold, pad=args.trim_pad)
                T_trimmed = seq["global_orient"].shape[0]
                print(f"   Sau trim: {T_trimmed} frames (bỏ {T_raw - T_trimmed} frames idle)")

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

            np.savez(out_path, **amass)
            print(f"   Đã lưu: {out_path}")
            # print(f"     poses={amass['poses'].shape}, trans={amass['trans'].shape}")

            succeeded.append(clip_name)
            if args.also_merge:
                merge_seqs.append(seq)

        except Exception as e:
            print(f"   Lỗi [{clip_name}]: {e}")
            failed.append((clip_name, str(e)))

    # ── (optional) merge tất cả thành 1 file lớn ────────────────────────────
    if args.also_merge and merge_seqs:
        print(f"\n{'='*60}")
        print(f" merging {len(merge_seqs)} sequence(s) → 1 file tổng hợp...")
        merged = {k: np.concatenate([s[k] for s in merge_seqs], axis=0) for k in KEYS}
        merge_out = args.merge_out or os.path.join(args.out_dir, "ALL_merged_amass.npz")

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
        np.savez(merge_out, **amass_merged)
        T_total = amass_merged["poses"].shape[0]
        print(f"✓ Đã lưu merge: {merge_out}  (tổng {T_total} frames)")

    # ── Tổng kết ─────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Hoàn thành: {len(succeeded)}/{len(folders)} folder(s) thành công")
    if failed:
        print(f"Thất bại ({len(failed)}):")
        for name, err in failed:
            print(f"   - {name}: {err}")
    print(f"Output directory: {os.path.abspath(args.out_dir)}")


if __name__ == "__main__":
    main()
