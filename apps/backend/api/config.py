import os
import re
from pathlib import Path

_HERE = Path(__file__).parent.parent.resolve()
_REPO_ROOT = _HERE.parent.parent.resolve()
_PROJECT_ROOT = Path(os.getenv("TEXT2SIGN_DATA_ROOT", str(_REPO_ROOT))).resolve()

_DEFAULT_SMPLX_MODEL = Path(
    os.getenv("SMPLX_MODEL_PATH", str(_REPO_ROOT / "models" / "smplx" / "SMPLX_NEUTRAL.npz"))
).resolve()

DEFAULT_ROOT = Path(
    os.getenv("SMPLERX_OUTPUT_DIR", str(_REPO_ROOT / "runtime" / "smplerx"))
).resolve()
DEFAULT_XBOT_FBX = Path(
    os.getenv("XBOT_FBX_PATH", str(_HERE / "XBOTXBOT.fbx"))
).resolve()
DEFAULT_AMASS_DIR = Path(
    os.getenv("AMASS_OUTPUT_DIR", str(_REPO_ROOT / "runtime" / "amass"))
).resolve()
DEFAULT_OUTPUT_DIR = Path(
    os.getenv("FBX_OUTPUT_DIR", str(_REPO_ROOT / "runtime" / "fbx"))
).resolve()

# Database & Redis settings
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/fbxviewer",
)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]
