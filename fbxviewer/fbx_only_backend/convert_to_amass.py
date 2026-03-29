#!/usr/bin/env python3
"""
Convert per-frame SMPL-X .npz files (or a merged sequence .npz) to AMASS-style .npz format.

AMASS SMPL-X format:
  poses         : (T, 165)  float32
                    [0:3]   global_orient  (1 joint  × 3)
                    [3:66]  body_pose      (21 joints × 3)
                    [66:69] jaw_pose       (1 joint  × 3)
                    [69:72] leye_pose      (1 joint  × 3)
                    [72:75] reye_pose      (1 joint  × 3)
                    [75:120] left_hand_pose (15 joints × 3)
                    [120:165] right_hand_pose (15 joints × 3)
  betas         : (16,)     float32   (shape params, first 10 used, rest padded)
  trans         : (T, 3)    float32
  expression    : (T, 10)   float32   (SMPL-X face expression — bonus)
  mocap_framerate: float    (default 30)
  gender        : str       'neutral' | 'male' | 'female'

Usage
-----
# From a folder of per-frame .npz files:
  python convert_to_amass.py --src output_smplerx/D0001B/smplx --out D0001B_amass.npz

# From an already-merged sequence .npz (like sequence_smplx.npz):
  python convert_to_amass.py --src sequence_smplx.npz --out D0001B_amass.npz --fps 30
"""

import os
import re
import argparse
import numpy as np
from scipy.spatial.transform import Rotation as R
from scipy.signal import savgol_filter
from tqdm import tqdm


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def load_from_folder(folder: str):
    """Load per-frame .npz files from a folder and stack them."""
    npz_files = [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(".npz")
    ]
    npz_files = sorted(npz_files, key=lambda p: natural_key(os.path.basename(p)))
    assert len(npz_files) > 0, f"No .npz files found in {folder}"

    keys = [
        "global_orient", "body_pose",
        "left_hand_pose", "right_hand_pose",
        "jaw_pose", "leye_pose", "reye_pose",
        "betas", "expression", "transl",
    ]
    buffers = {k: [] for k in keys}

    for path in tqdm(npz_files, desc="Loading frames"):
        d = np.load(path)
        for k in keys:
            buffers[k].append(np.asarray(d[k]).astype(np.float32))

    return {k: np.stack(buffers[k], axis=0) for k in keys}


def load_from_merged(path: str):
    """Load an already-merged sequence .npz (shape: (T, ...) per key)."""
    d = np.load(path)
    return {k: np.asarray(d[k]).astype(np.float32) for k in d.files}


# ---------------------------------------------------------------------------
# core conversion
# ---------------------------------------------------------------------------

def to_amass(seq: dict, fps: float = 30.0, gender: str = "neutral",
             betas_dim: int = 16,
             fix_global_orient: bool = True,
             add_hands_mean: bool = True,
             smooth_trans: bool = True,
             smooth_poses: bool = False,
             smooth_poses_window: int = 7,
             zero_trans: bool = False,
             zero_legs: bool = False,
             smplx_model_path: str = "models/smplx/SMPLX_NEUTRAL.npz") -> dict:
    """
    Convert a dict of SMPL-X sequence arrays to AMASS-style dict.

    Coordinate fix (confirmed by testing in Blender SMPL-X addon v4.2):
      SMPLer-X outputs global_orient in OpenCV camera space (Y-down, Z-forward).
      The Blender AMASS addon applies its own root-bone Rx(-90°) for Y-up→Z-up,
      but that cancels differently than expected due to bone-local axes.
      Empirical test showed: pre-multiplying global_orient by Rx(-90°) produces
      a correctly standing body in Blender AMASS mode.

    Default fixes:
      fix_global_orient : Rx(-90°) @ each frame's global_orient  [on by default]
      add_hands_mean    : add SMPL-X hands_mean to hand pose vectors [on by default]
      smooth_trans      : Savitzky-Golay filter on translation [on by default]
      zero_trans        : zero out all translation (opt-in, great for sign language)
    """

    def squeeze_to_2d(arr, expected_last):
        """(T, 1, D) → (T, D)  or  (T, D) → (T, D)"""
        arr = np.asarray(arr, dtype=np.float32)
        if arr.ndim == 3 and arr.shape[1] == 1:
            arr = arr[:, 0, :]          # (T, 1, D) → (T, D)
        elif arr.ndim == 3:
            arr = arr.reshape(arr.shape[0], -1)  # (T, J, 3) → (T, J*3)
        return arr

    T = seq["global_orient"].shape[0]

    # ── global_orient: fix from OpenCV camera space → world Y-up ─────────────
    # SMPLer-X outputs global_orient in OpenCV camera space (Y↓, Z→screen).
    # global_orient ≈ [π, 0, 0] means the body faces down (lying flat).
    # Fix: pre-multiply by Rx(-π) to flip Y and Z, making the body stand upright.
    global_orient_raw = squeeze_to_2d(seq["global_orient"], 3)  # (T, 3)
    
    if zero_legs:
        # Fix: The neutral global orient in SMPLer-X (OpenCV space) is [pi, 0, 0], not [0, 0, 0].
        # If we set it to 0, applying Rx(-90) later makes the character upside down.
        global_orient_raw = np.zeros_like(global_orient_raw)
        global_orient_raw[:, 0] = np.pi

    if fix_global_orient:
        # Empirically confirmed: Rx(-90°) pre-multiplied on each frame's global_orient
        # produces a correctly standing body in Blender SMPL-X addon AMASS mode.
        Rx_neg90 = R.from_euler("x", -90, degrees=True).as_matrix()  # 3×3
        fixed = []
        for aa in global_orient_raw:
            R_orig = R.from_rotvec(aa).as_matrix()
            R_fixed = Rx_neg90 @ R_orig
            fixed.append(R.from_matrix(R_fixed).as_rotvec())
        global_orient = np.array(fixed, dtype=np.float32)  # (T, 3)
    else:
        global_orient = global_orient_raw

    # ── hand pose: add SMPL-X hands_mean ─────────────────────────────────────
    # The Python smplx library automatically adds hands_mean before decoding,
    # but the Blender SMPL-X addon does NOT → raw hand pose looks wrong.
    lhp = squeeze_to_2d(seq["left_hand_pose"],  45)  # (T, 45)
    rhp = squeeze_to_2d(seq["right_hand_pose"], 45)  # (T, 45)
    if add_hands_mean:
        try:
            model_data = np.load(smplx_model_path, allow_pickle=True)
            hands_meanl = model_data["hands_meanl"].astype(np.float32)  # (45,)
            hands_meanr = model_data["hands_meanr"].astype(np.float32)  # (45,)
            lhp = lhp + hands_meanl[np.newaxis, :]  # broadcast over T
            rhp = rhp + hands_meanr[np.newaxis, :]  # broadcast over T
            # print(f"  Added hands_mean (|mean_l|={np.abs(hands_meanl).max():.3f})")
        except Exception as e:
            print(f"  Could not load hands_mean from {smplx_model_path}: {e}")

    # ── remaining pose parts ──────────────────────────────────────────────────
    body_pose = squeeze_to_2d(seq["body_pose"],  63)  # (T, 63)

    # ── zero_legs: zero out các joint của chân → giữ T-pose ─────────────────
    # SMPL-X body_pose joint order (each joint = 3 dims):
    # 0=L_Hip 1=R_Hip 2=Spine1 3=L_Knee 4=R_Knee 5=Spine2
    # 6=L_Ankle 7=R_Ankle 8=Spine3 9=L_Foot 10=R_Foot ...
    if zero_legs:
        LEG_JOINTS = [0, 1, 3, 4, 6, 7, 9, 10]  # L/R: Hip, Knee, Ankle, Foot
        for j in LEG_JOINTS:
            body_pose[:, j*3 : j*3+3] = 0.0
        # print(f"  ✓ Zero legs: đã zero {len(LEG_JOINTS)} leg joints (chân giữ T-pose)")

    jaw_pose  = squeeze_to_2d(seq["jaw_pose"],    3)  # (T, 3)
    leye_pose = squeeze_to_2d(seq["leye_pose"],   3)  # (T, 3)
    reye_pose = squeeze_to_2d(seq["reye_pose"],   3)  # (T, 3)

    # ── poses: concatenate in AMASS SMPL-X joint order ───────────────────────
    # [0:3] global_orient | [3:66] body | [66:69] jaw | [69:72] leye
    # [72:75] reye | [75:120] left_hand | [120:165] right_hand
    poses = np.concatenate(
        [global_orient, body_pose, jaw_pose, leye_pose, reye_pose, lhp, rhp],
        axis=1,  # → (T, 165)
    )
    # assert poses.shape == (T, 165), f"Expected (T, 165) got {poses.shape}"

    # ── smooth_poses: SavGol filter trên joint rotations để giảm jitter ────────────
    if smooth_poses and T >= smooth_poses_window:
        win = smooth_poses_window if smooth_poses_window % 2 == 1 else smooth_poses_window + 1
        poses = savgol_filter(poses, window_length=win, polyorder=3, axis=0)
        poses = poses.astype(np.float32)
        # print(f"  ✓ Pose smoothed ( window={win})")

    raw_betas = seq["betas"]  # (T, 1, 10) or (T, 10) or (1, 10)
    raw_betas = raw_betas.reshape(-1, raw_betas.shape[-1])   # (T, 10) or (1, 10)
    betas_mean = raw_betas.mean(axis=0)                       # (10,)
    betas = np.zeros(betas_dim, dtype=np.float32)
    copy_len = min(betas_mean.shape[0], betas_dim)
    betas[:copy_len] = betas_mean[:copy_len]                  # (16,)

    # ── trans: center + smooth to remove jitter ───────────────────────────────
    trans = squeeze_to_2d(seq["transl"], 3)  # (T, 3)
    trans = trans - trans[0:1]               # center to origin
    if zero_trans or zero_legs:
        trans = np.zeros_like(trans)
        print("  ✓ Translation zeroed out (model stays at origin)")
    elif smooth_trans and T >= 11:
        win = min(11, T if T % 2 == 1 else T - 1)
        trans = savgol_filter(trans, window_length=win, polyorder=3, axis=0)
        trans = trans.astype(np.float32)
        print(f"  ✓ Translation smoothed (Savitzky-Golay window={win})")

    # ── expression ────────────────────────────────────────────────────────────
    expression = squeeze_to_2d(seq["expression"], 10)  # (T, 10)

    # np.savez wraps Python scalars/strings into numpy arrays.
    # gender as bytes, framerate as float64 scalar.
    gender_arr = np.array(gender)          # dtype='<U7', str() → 'neutral' ✓
    fps_arr    = np.array(float(fps), dtype=np.float64)

    return {
        "poses":            poses,
        "betas":            betas,
        "trans":            trans,
        "expression":       expression,
        "mocap_framerate":  fps_arr,
        "gender":           gender_arr,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert SMPL-X sequence to AMASS-style .npz"
    )
    parser.add_argument("--src", required=True,
        help="Folder of per-frame .npz files OR a merged sequence .npz")
    parser.add_argument("--out", default="amass_style.npz",
        help="Output .npz path (default: amass_style.npz)")
    parser.add_argument("--fps", type=float, default=30.0,
        help="Frames per second (default: 30)")
    parser.add_argument("--gender", default="neutral",
        choices=["neutral", "male", "female"])
    parser.add_argument("--zero-trans", action="store_true",
        help="Zero out all translation; model stays at origin (removes jitter completely)")
    parser.add_argument("--no-smooth-trans", action="store_true",
        help="Do not apply Savitzky-Golay smoothing to translation")
    parser.add_argument("--no-fix-orient", action="store_true",
        help="Do not apply global_orient rotation fix (skip Rx(-pi) correction)")
    parser.add_argument("--no-hands-mean", action="store_true",
        help="Do not add SMPL-X hands_mean to hand pose")
    parser.add_argument("--smplx-model-path", default="models/smplx/SMPLX_NEUTRAL.npz",
        help="Path to SMPLX_NEUTRAL.npz for hands_mean (default: models/smplx/SMPLX_NEUTRAL.npz)")
    args = parser.parse_args()

    # Load source
    if os.path.isdir(args.src):
        print(f"Loading from folder: {args.src}")
        seq = load_from_folder(args.src)
    elif args.src.endswith(".npz"):
        print(f"Loading from merged .npz: {args.src}")
        seq = load_from_merged(args.src)
    else:
        raise ValueError(f"--src must be a folder or .npz file")

    T = seq["global_orient"].shape[0]
    print(f"Total frames: {T}")
    print("Applying fixes:")

    amass = to_amass(
        seq,
        fps=args.fps,
        gender=args.gender,
        fix_global_orient=not args.no_fix_orient,
        add_hands_mean=not args.no_hands_mean,
        smooth_trans=not args.no_smooth_trans,
        zero_trans=args.zero_trans,
        smplx_model_path=args.smplx_model_path,
    )

    np.savez(args.out, **amass)
    print(f"\n✓ Saved: {args.out}")
    print("Shapes:")
    for k, v in amass.items():
        arr = np.asarray(v)
        val = repr(arr.item()) if arr.size == 1 else arr.shape
        print(f"  {k:20s} {val}  dtype={arr.dtype}")


if __name__ == "__main__":
    main()

