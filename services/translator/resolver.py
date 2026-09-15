from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


class SignResolver:
    """Resolve canonical dictionary text produced by VnTokenizer to sign clip IDs."""

    def __init__(self, csv_path: str | Path):
        self.csv_path = Path(csv_path)
        self._exact: dict[str, str] = {}
        self._folded: dict[str, str] = {}
        self._load()

    @staticmethod
    def _select_variant(rows: list[dict[str, str]]) -> dict[str, str] | None:
        # Match the tokenizer's dictionary preference: B variant first, then a
        # non B/N/T variant, then fall back to the first available row.
        for row in rows:
            image_id = (row.get("image_id") or "").strip()
            if image_id.endswith("B"):
                return row
        for row in rows:
            image_id = (row.get("image_id") or "").strip()
            if image_id and not image_id.endswith(("B", "N", "T")):
                return row
        return rows[0] if rows else None

    def _load(self) -> None:
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Dictionary not found: {self.csv_path}")

        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                text = (row.get("text") or "").strip()
                image_id = (row.get("image_id") or "").strip()
                if text and image_id:
                    grouped[text].append(row)

        for text, rows in grouped.items():
            chosen = self._select_variant(rows)
            if not chosen:
                continue
            image_id = (chosen.get("image_id") or "").strip()
            self._exact[text] = image_id
            # Do not overwrite the first canonical spelling when case-folded
            # entries collide.
            self._folded.setdefault(text.casefold(), image_id)

    @property
    def size(self) -> int:
        return len(self._exact)

    def resolve(self, token: str) -> str | None:
        token = token.strip()
        if not token:
            return None
        if token in self._exact:
            return self._exact[token]
        return self._folded.get(token.casefold())

    def resolve_many(self, tokens: list[str]) -> tuple[list[str], list[str]]:
        videos: list[str] = []
        unresolved: list[str] = []
        for token in tokens:
            image_id = self.resolve(token)
            if image_id:
                videos.append(image_id)
            else:
                unresolved.append(token)
        return videos, unresolved
