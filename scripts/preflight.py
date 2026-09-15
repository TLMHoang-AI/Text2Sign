#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
checks = {
    "dictionary": ROOT / "data" / "dictionaries" / "dictionary_data.csv",
    "xbot rig": ROOT / "apps" / "backend" / "XBOTXBOT.fbx",
    "SMPL-X neutral model": ROOT / "models" / "smplx" / "SMPLX_NEUTRAL.npz",
    "SMPLer-X sign assets": ROOT / "runtime" / "smplerx",
}

failed = False
for label, path in checks.items():
    if label == "SMPLer-X sign assets":
        ok = path.is_dir() and any(p.is_dir() for p in path.iterdir())
    else:
        ok = path.exists()
    mark = "OK" if ok else "MISSING"
    print(f"[{mark:7}] {label}: {path}")
    failed = failed or not ok

if failed:
    print("\nRuntime assets are incomplete. Source services can still build, but the full text-to-FBX pipeline cannot complete until the missing assets are provisioned.")
    sys.exit(1)

print("\nRequired runtime assets are present.")
