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


_STOPWORDS = {
    "the", "a", "an", "in", "on", "at", "of", "for", "to", "by", "with", "and",
    "or", "as", "is", "are", "was", "were", "be", "been", "after", "over",
    "amid", "against", "regarding", "about", "from", "its", "his", "her",
}


def _tokens(text: str) -> set:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def is_duplicate(headline: str, topic: str, history: list, threshold: float = 0.55) -> bool:
    """Deterministic backstop for Gemini's semantic dedup: if the composed
    headline/topic shares most of its words with something already posted,
    it's the same story reworded."""
    new = _tokens(headline) | _tokens(topic)
    if not new:
        return False
    for e in history:
        old = _tokens(e.get("headline", "")) | _tokens(e.get("topic", ""))
        if not old:
            continue
        overlap = len(new & old) / len(new | old)
        if overlap >= threshold:
            print(f"  [dedup] '{headline[:60]}' matches posted '{e.get('headline', '')[:60]}' ({overlap:.2f})")
            return True
    return False


def load_queue() -> list:
    if os.path.exists(config.QUEUE_FILE):
        with open(config.QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_queue(queue: list) -> None:
    os.makedirs(os.path.dirname(config.QUEUE_FILE), exist_ok=True)
    with open(config.QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=1)
