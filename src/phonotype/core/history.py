"""Dictation history: what was recognised and what was typed, kept on disk.

One JSON object per line in ``~/.local/share/phonotype/history.jsonl`` (mode
0600 — it is everything the user dictated):

    {"ts": "2026-11-24T16:34:58", "text": "<typed>", "raw": "<recognised>",
     "model": "ggml-….bin", "prompt": "default"}

``raw`` is present only when AI processing changed the text; ``prompt`` only
when AI processing ran. Entries older than ``history_days`` are dropped when a
new one is added (0 keeps everything). ``history_enabled: false`` stops
recording; what is already stored stays until cleared.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from phonotype.utils.libw import verr

FILE_NAME = "history.jsonl"


def history_path() -> Path:
    from phonotype.paths import DATA_DIR
    return DATA_DIR / FILE_NAME


def _read(path: Path) -> list[dict]:
    entries: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue            # a torn line must not hide the rest
                if isinstance(item, dict) and item.get("ts") and item.get("text"):
                    entries.append(item)
    except FileNotFoundError:
        pass
    except OSError as e:
        verr(f"[history] Cannot read {path}: {e}")
    return entries


def _write(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for item in entries:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def load() -> list[dict]:
    """All stored entries, newest first."""
    return list(reversed(_read(history_path())))


def last_text() -> str:
    entries = _read(history_path())
    return entries[-1]["text"] if entries else ""


def add(text: str, raw: str | None = None, *, cfg_data: dict | None = None,
        model: str | None = None, prompt: str | None = None,
        now: datetime | None = None) -> dict | None:
    """Record one dictation; returns the entry, or None when history is off
    or there is nothing to record."""
    data = cfg_data or {}
    text = (text or "").strip()
    if not text or not data.get("history_enabled", True):
        return None
    now = now or datetime.now()
    entry: dict = {"ts": now.isoformat(timespec="seconds"), "text": text}
    raw = (raw or "").strip()
    if raw and raw != text:
        entry["raw"] = raw
    if model:
        entry["model"] = model
    if prompt:
        entry["prompt"] = prompt

    path = history_path()
    try:
        entries = prune(_read(path), data.get("history_days", 30), now) + [entry]
        _write(path, entries)
    except OSError as e:
        verr(f"[history] Cannot write {path}: {e}")
        return None
    return entry


def prune(entries: list[dict], days, now: datetime | None = None) -> list[dict]:
    """Entries not older than *days* (0 or invalid: keep all)."""
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 0
    if days <= 0:
        return list(entries)
    limit = ((now or datetime.now()) - timedelta(days=days)).isoformat(timespec="seconds")
    return [e for e in entries if str(e.get("ts", "")) >= limit]


def search(entries: list[dict], query: str) -> list[dict]:
    """Entries whose typed or recognised text contains every word of *query*."""
    words = (query or "").casefold().split()
    if not words:
        return list(entries)
    found = []
    for e in entries:
        haystack = (e.get("text", "") + "\n" + e.get("raw", "")).casefold()
        if all(w in haystack for w in words):
            found.append(e)
    return found


def delete(ts: str) -> None:
    path = history_path()
    entries = _read(path)
    kept = [e for e in entries if e.get("ts") != ts]
    if len(kept) != len(entries):
        _write(path, kept)


def clear() -> None:
    try:
        history_path().unlink()
    except FileNotFoundError:
        pass
