from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from text2sign.nlp.tokenizer import VnTokenizer
from resolver import SignResolver

DICTIONARY_PATH = Path(
    os.getenv("DICTIONARY_PATH", "/data/dictionaries/dictionary_data.csv")
).resolve()
STRICT = os.getenv("TRANSLATOR_STRICT", "true").strip().lower() in {
    "1", "true", "yes", "on"
}

app = FastAPI(
    title="Text2Sign Translator Service",
    description="Vietnamese text -> canonical sign tokens -> sign clip IDs",
    version="1.0.0",
)

# Load once at process startup. This is intentionally fail-fast: a missing or
# malformed dictionary should stop the service instead of producing random clips.
tokenizer = VnTokenizer(str(DICTIONARY_PATH), finger_spell_names=True)
resolver = SignResolver(DICTIONARY_PATH)


class TranslateRequest(BaseModel):
    sentence: str


@app.get("/health")
def health():
    return {
        "status": "ok",
        "dictionary": str(DICTIONARY_PATH),
        "entries": resolver.size,
        "strict": STRICT,
    }


@app.post("/translate")
def translate(req: TranslateRequest):
    sentence = req.sentence.strip()
    if not sentence:
        raise HTTPException(status_code=400, detail="Sentence is empty")

    tokens = tokenizer.tokenize(sentence)
    videos, unresolved = resolver.resolve_many(tokens)

    if STRICT and unresolved:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Some tokens could not be resolved to sign clips",
                "tokens": tokens,
                "unresolved": unresolved,
            },
        )

    if not videos:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No sign clips could be resolved",
                "tokens": tokens,
                "unresolved": unresolved,
            },
        )

    # Keep `videos` compatible with the existing backend contract. Extra fields
    # are diagnostic and are ignored by the current backend.
    return {
        "videos": videos,
        "tokens": tokens,
        "unresolved": unresolved,
    }
