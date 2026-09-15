import os
import re
from pathlib import Path

_HERE = Path(__file__).parent.parent.resolve()
_PROJECT_ROOT = _HERE.parent.parent
_DEFAULT_SMPLX_MODEL = _PROJECT_ROOT / "models" / "smplx" / "SMPLX_NEUTRAL.npz"

DEFAULT_ROOT        = _PROJECT_ROOT / "output_smplerx"
DEFAULT_XBOT_FBX    = _HERE / "XBOTXBOT.fbx"
DEFAULT_AMASS_DIR   = _HERE / "amass_output"
DEFAULT_OUTPUT_DIR  = _HERE / "xbot_retargeted"

# Database & Redis Settings
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/fbxviewer")
REDIS_HOST   = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT   = int(os.getenv("REDIS_PORT", "6379"))

def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]
