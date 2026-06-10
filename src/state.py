"""Posted-history persistence. The JSON file is committed back to the repo by
the workflow, so history survives between Actions runs."""
import hashlib
import json
import os
import re
from datetime import datetime, timezone

from . import config


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_title(title: str) -> str:
    t = re.sub(r"\s+", " ", (title or "").strip().lower())
    return re.sub(r"[^\wঀ-৿ ]", "", t)


def title_hash(title: str) -> str:
    return hashlib.sha1(norm_title(title).encode("utf-8")).hexdigest()[:16]


def load_history() -> list:
    if os.path.exists(config.STATE_FILE):
        with open(config.STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history: list) -> None:
    history = history[-config.HISTORY_KEEP:]
    os.makedirs(os.path.dirname(config.STATE_FILE), exist_ok=True)
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=1)


def seen_keys(history: list) -> set:
    keys = set()
    for e in history:
        if e.get("url"):
            keys.add(e["url"])
        if e.get("title_hash"):
            keys.add(e["title_hash"])
    return keys


def record(history: list, item: dict, status: str) -> None:
    history.append({
        "title_hash": title_hash(item.get("orig_title") or item.get("headline", "")),
        "url": item.get("url", ""),
        "headline": item.get("headline", ""),
        "topic": item.get("topic", ""),
        "source": item.get("source", ""),
        "status": status,  # queued | posted | dry-run | failed
        "at": _now(),
    })


def load_queue() -> list:
    if os.path.exists(config.QUEUE_FILE):
        with open(config.QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_queue(queue: list) -> None:
    os.makedirs(os.path.dirname(config.QUEUE_FILE), exist_ok=True)
    with open(config.QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=1)
