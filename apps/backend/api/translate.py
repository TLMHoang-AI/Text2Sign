"""
api/translate.py — Endpoint POST /translate: submit pipeline vào task queue.
Trả task_id ngay, client poll GET /tasks/{id} để lấy kết quả kèm subtitle_timings + output_files.
"""

import numpy as np
from pathlib import Path
from fastapi import APIRouter, HTTPException
import requests as http_requests
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from .models import ConvertRequest, TranslateRequest, TranslationRequest as DBTranslationRequest
from .config import DEFAULT_AMASS_DIR, DEFAULT_OUTPUT_DIR
from .helpers import load_dictionary_mapping, split_sentences
from .pipeline import run_batch_convert_only, merge_amass_npz, run_retarget_only
from . import queue as tq
from .db import get_db, AsyncSessionLocal
from .users import get_current_user
from fastapi import Depends

router = APIRouter()

import os
TRANSLATE_API_URL = os.getenv("TRANSLATE_API_URL", "http://localhost:8001/translate")


# ─── Pipeline function (chạy trong background worker) ────────────────────────

def _translate_pipeline(sentence: str, record_id: int = None) -> dict:
    """Toàn bộ translate → amass → retarget pipeline, chạy ở background."""
    sentences = split_sentences(sentence)
    if not sentences:
        raise ValueError("Văn bản trống.")

    mapping     = load_dictionary_mapping()
    all_outputs = []
    all_amass   = []

    for idx, sent in enumerate(sentences, start=1):
        print(f"[Translate] {idx}/{len(sentences)}: {sent}")
        response = http_requests.post(TRANSLATE_API_URL, json={"sentence": sent}, timeout=30)
        response.raise_for_status()
        data = response.json()

        part_videos = data.get("videos", [])
        if not part_videos:
            raise ValueError(f"API không trả về video cho câu: {sent}")

        words             = [mapping.get(vid, vid) for vid in part_videos]
        sentence_subtitle = " ".join(words)

        merge_out   = str(DEFAULT_AMASS_DIR / f"ALL_merged_s{idx}_amass.npz")
        convert_req = ConvertRequest(
            folders=part_videos,
            merge_out=merge_out,
            fps=30.0,
            gender="neutral",
            trim_idle=True,
            trim_threshold=0.1,
            smooth_pose=True,
            pose_window=7,
            zero_legs=True,
            stabilize=True,
            rotate_x=-90.0,
        )

        result = run_batch_convert_only(convert_req)
        if result["status"] == "error":
            raise RuntimeError(result.get("error", "batch_convert failed"))
        if not result.get("merged_path"):
            raise RuntimeError("Không tạo được AMASS merge cho câu.")

        # Timing từng từ
        word_timings = []
        for word_idx, vid in enumerate(part_videos):
            vid_npz      = DEFAULT_AMASS_DIR / f"{vid}_amass.npz"
            duration_sec = 0.0
            if vid_npz.exists():
                try:
                    d            = np.load(str(vid_npz))
                    duration_sec = d["poses"].shape[0] / 30.0
                except Exception as e:
                    print(f"Lỗi load frame count cho {vid}: {e}")
            word_timings.append({"text": words[word_idx], "video": vid, "duration_sec": duration_sec})

        all_amass.append(result["merged_path"])
        all_outputs.append({
            "sentence"    : sent,
            "videos"      : part_videos,
            "amass"       : result.get("merged_path"),
            "subtitle"    : sentence_subtitle,
            "word_timings": word_timings,
        })

    # Merge AMASS + retarget
    if len(all_amass) == 1:
        final_amass = all_amass[0]
    else:
        final_amass = str(DEFAULT_AMASS_DIR / f"merged_{record_id or 'temp'}_amass.npz")
        merge_amass_npz(all_amass, final_amass)

    output_filename = f"out_{record_id or 'temp'}_{int(datetime.utcnow().timestamp())}.fbx"
    output_fbx      = str(DEFAULT_OUTPUT_DIR / output_filename)
    retarget_result = run_retarget_only(
        amass_npz=final_amass,
        output_fbx=output_fbx,
        fps=30.0,
        stabilize=True,
        rotate_x=-90.0,
    )
    if retarget_result["status"] == "error":
        raise RuntimeError(retarget_result.get("error", "retarget failed"))

    # Tổng hợp subtitle + timing
    final_subtitle = " ".join(o.get("subtitle", "") for o in all_outputs if o.get("subtitle")).strip()
    final_timings  = []
    current_start  = 0.0
    for out in all_outputs:
        for w in out.get("word_timings", []):
            duration = w["duration_sec"]
            final_timings.append({
                "text"      : w["text"],
                "start_time": current_start,
                "end_time"  : current_start + duration,
            })
            current_start += duration

    # Cập nhật DB nếu có record_id
    if record_id:
        async def update_db():
            async with AsyncSessionLocal() as db:
                from sqlalchemy import update
                await db.execute(
                    update(DBTranslationRequest)
                    .where(DBTranslationRequest.id == record_id)
                    .values(status="done", videos=output_filename) # Store the unique filename
                )
                await db.commit()
        
        # Chạy cập nhật DB trong thread khác vì worker có thể không handle được async loop tốt tùy config
        # Nhưng ở đây tq.worker dùng asyncio, nên ta có thể chạy async update
        import asyncio
        try:
            asyncio.run(update_db())
        except Exception as e:
            print(f"Lỗi cập nhật DB: {e}")

    return {
        "status"           : "success",
        "items"            : all_outputs,
        "merged_amass"     : final_amass,
        "output_files"     : [Path(output_fbx).name],
        "subtitle_text"    : final_subtitle,
        "subtitle_timings" : final_timings,
    }


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/translate", summary="Translate text → pipeline (async, trả task_id ngay)")
async def translate_and_convert(
    req: TranslateRequest, 
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user) # Bắt buộc login để lưu history
):
    # Lưu vào database trước
    new_request = DBTranslationRequest(
        user_id=current_user.id,
        sentence=req.sentence,
        status="pending"
    )
    db.add(new_request)
    await db.commit()
    await db.refresh(new_request)

    task_id = await tq.submit("_translate_pipeline", req.sentence, record_id=new_request.id)
    return {
        "task_id": task_id, 
        "request_id": new_request.id,
        "status": "pending", 
        "poll": f"/tasks/{task_id}"
    }
