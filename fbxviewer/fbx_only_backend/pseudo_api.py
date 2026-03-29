from fastapi import FastAPI
from pydantic import BaseModel
import random
from pathlib import Path

app = FastAPI()

class TranslateRequest(BaseModel):
    sentence: str

# Directory that contains all generated poses
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output_smplerx"

def get_valid_ids():
    if OUTPUT_DIR.exists():
        return [d.name for d in OUTPUT_DIR.iterdir() if d.is_dir() and (d.name.startswith("D") or d.name.startswith("W"))]
    return ["W0417", "W02876"]

VALID_IDS = get_valid_ids()

@app.post("/translate")
def translate(req: TranslateRequest):
    print(f"[Pseudo API] Nhận câu: {req.sentence}")
    # Trả về số lượng video tương ứng với số từ trong câu (tối đa 3 để render nhanh)
    words = req.sentence.split()
    num_videos = min(len(words), 3)
    if not num_videos:
        num_videos = 1
        
    videos = random.sample(VALID_IDS, min(num_videos, len(VALID_IDS)))
    print(f"[Pseudo API] Trả về videos pseudo: {videos}")
    
    return {"videos": videos}

if __name__ == "__main__":
    import uvicorn
    # Chạy trên port 8001 để không trùng với backend chính (8765)
    print("Khởi động Pseudo Translation API trên http://localhost:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)
