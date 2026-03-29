from fastapi import APIRouter
from .config import DEFAULT_ROOT, natural_key

router = APIRouter()

@router.get("/clips", summary="Liệt kê các clip folder trong output_smplerx/")
def list_clips():
    root = DEFAULT_ROOT
    if not root.exists():
        return {"clips": [], "root": str(root)}

    clips = []
    for d in sorted(root.iterdir(), key=lambda p: natural_key(p.name)):
        if not d.is_dir(): continue
        smplx_dir  = d / "smplx"
        has_smplx  = smplx_dir.is_dir()
        pkl_count  = len(list(smplx_dir.glob("*.pkl"))) if has_smplx else 0
        clips.append({"name": d.name, "has_smplx": has_smplx, "smplx_files": pkl_count})

    return {"clips": clips, "root": str(root)}
