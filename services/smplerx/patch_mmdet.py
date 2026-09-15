from __future__ import annotations

import sys
from pathlib import Path


def patch_mmdet_init(mmdet_root: str = "/kaggle/working/mmdetection") -> bool:
    """
    Patch mmdet/__init__.py to allow MMCV==2.2.0.
    Original logic:
        mmcv_version < digit_version(mmcv_maximum_version)
    Patched logic:
        mmcv_version <= digit_version(mmcv_maximum_version)
    """
    target = Path(mmdet_root) / "mmdet" / "__init__.py"

    if not target.exists():
        print(f"[mmdet] File not found: {target}")
        return False

    text = target.read_text(encoding="utf-8")

    old = "mmcv_version < digit_version(mmcv_maximum_version)"
    new = "mmcv_version <= digit_version(mmcv_maximum_version)"

    if new in text:
        print(f"[mmdet] Already patched: {target}")
        return True

    if old not in text:
        print(f"[mmdet] Pattern not found in: {target}")
        return False

    text = text.replace(old, new)
    target.write_text(text, encoding="utf-8")
    print(f"[mmdet] Patched: {target}")
    return True


def patch_mmengine_checkpoint(
    checkpoint_file: str = "/usr/local/lib/python3.12/dist-packages/mmengine/runner/checkpoint.py",
) -> bool:
    """
    Patch mmengine checkpoint loader to force weights_only=False for torch.load(),
    avoiding PyTorch >=2.6 default behavior that breaks older OpenMMLab checkpoints.
    """
    target = Path(checkpoint_file)

    if not target.exists():
        print(f"[mmengine] File not found: {target}")
        return False

    text = target.read_text(encoding="utf-8")

    old = "checkpoint = torch.load(filename, map_location=map_location)"
    new = "checkpoint = torch.load(filename, map_location=map_location, weights_only=False)"

    if new in text:
        print(f"[mmengine] Already patched: {target}")
        return True

    if old not in text:
        print(f"[mmengine] Pattern not found in: {target}")
        return False

    text = text.replace(old, new)
    target.write_text(text, encoding="utf-8")
    print(f"[mmengine] Patched: {target}")
    return True


def main() -> int:
    print("=== Patching OpenMMLab stack on Kaggle ===")

    ok1 = patch_mmdet_init("/kaggle/working/mmdetection")
    ok2 = patch_mmengine_checkpoint(
        "/usr/local/lib/python3.12/dist-packages/mmengine/runner/checkpoint.py"
    )

    print("\n=== Summary ===")
    print(f"mmdet patch:    {'OK' if ok1 else 'FAILED'}")
    print(f"mmengine patch: {'OK' if ok2 else 'FAILED'}")

    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    raise SystemExit(main())