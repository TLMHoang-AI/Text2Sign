from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from .config import DEFAULT_OUTPUT_DIR, natural_key

router = APIRouter()

@router.get("/fbx", summary="Liệt kê các file FBX đã output")
def list_fbx():
    out_dir = DEFAULT_OUTPUT_DIR
    if not out_dir.exists():
        return {"files": [], "output_dir": str(out_dir)}

    files = []
    for f in sorted(out_dir.glob("*.fbx"), key=lambda p: natural_key(p.name)):
        stat = f.stat()
        files.append({
            "filename"   : f.name,
            "size_mb"    : round(stat.st_size / 1_048_576, 2),
            "modified_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
            "download_url": f"/fbx/{f.name}",
        })
    return {"files": files, "output_dir": str(out_dir)}


@router.get("/fbx/{filename}", summary="Download file FBX")
def download_fbx(filename: str):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Tên file không hợp lệ")

    path = DEFAULT_OUTPUT_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"File '{filename}' không tồn tại")

    return FileResponse(path=str(path), media_type="application/octet-stream", filename=filename)
