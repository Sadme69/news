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


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _tokens(text: str) -> set:
    words = re.findall(r"[a-z]+", (text or "").lower())
    return {_stem(w) for w in words if w not in _STOPWORDS and len(w) > 2}


def _numbers(text: str) -> set:
    """Distinctive figures ('9.38', '404', '6.5') are the strongest same-story
    signal there is. Plain years are too generic to count."""
    out = set()
    for n in re.findall(r"\d+(?:\.\d+)?", text or ""):
        if re.fullmatch(r"(19|20)\d{2}", n) or len(n) < 2:
            continue
        out.add(n)
    return out


def is_duplicate(headline: str, topic: str, history: list, threshold: float = 0.5) -> bool:
    """Deterministic backstop for Gemini's semantic dedup. Two triggers:
    high word overlap (same story reworded), or a shared distinctive figure
    plus several shared content words (same event at a different stage,
    e.g. 'budget to be presented' -> 'budget unveiled')."""
    new_words = _tokens(headline) | _tokens(topic)
    new_nums = _numbers(headline) | _numbers(topic)
    if not new_words:
        return False
    for e in history:
        old_text = f"{e.get('headline', '')} {e.get('topic', '')}"
        old_words = _tokens(old_text)
        if not old_words:
            continue
        shared_words = new_words & old_words
        overlap = len(shared_words) / len(new_words | old_words)
        shared_nums = new_nums & _numbers(old_text)
        if overlap >= threshold or (shared_nums and len(shared_words) >= 3):
            print(f"  [dedup] '{headline[:60]}' matches posted '{e.get('headline', '')[:60]}' "
                  f"(overlap={overlap:.2f}, shared figures={sorted(shared_nums)})")
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
