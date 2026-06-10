"""API-call budget ledger.

Usage counters live in state/api_usage.json (committed back to the repo by the
workflow, like the posting history), so budgets survive between Actions runs.
Buckets roll over automatically: day counters reset at midnight UTC, month
counters on the 1st."""
import json
import os
from datetime import datetime, timezone

from . import config

FILE = os.path.join(config.ROOT, "state", "api_usage.json")

_data = None


def _load() -> dict:
    global _data
    if _data is None:
        if os.path.exists(FILE):
            with open(FILE, "r", encoding="utf-8") as f:
                _data = json.load(f)
        else:
            _data = {}
    return _data


def save() -> None:
    if _data is None:
        return
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(_data, f, indent=1)


def _stamp(period: str) -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m") if period == "month" else now.strftime("%Y-%m-%d")


def used(key: str, period: str = "day") -> int:
    bucket = _load().get(key, {})
    return int(bucket.get(_stamp(period), 0))


def spend(key: str, n: int = 1, period: str = "day") -> None:
    data = _load()
    stamp = _stamp(period)
    bucket = data.setdefault(key, {})
    for k in list(bucket):  # drop stale buckets so the file stays tiny
        if k != stamp:
            del bucket[k]
    bucket[stamp] = int(bucket.get(stamp, 0)) + n
    save()


def remaining(key: str, limit: int, period: str = "day") -> int:
    return max(0, limit - used(key, period))


def exhaust(key: str, limit: int, period: str = "day") -> None:
    """Mark a budget as fully used (e.g. after the API returned 429)."""
    data = _load()
    stamp = _stamp(period)
    data.setdefault(key, {})[stamp] = limit
    save()


# ---- service-specific helpers ----
# Gemini quotas apply per API key per model, so budgets are tracked for each
# (key, model) pair. Key index 0 = primary, 1 = backup.

def _gemini_limit(model: str) -> int:
    return config.GEMINI_DAILY_LIMITS.get(model, config.GEMINI_DEFAULT_DAILY_LIMIT)


def gemini_pair_key(key_idx: int, model: str) -> str:
    return f"gemini:{key_idx}:{model}"


def gemini_pair_remaining(key_idx: int, model: str) -> int:
    return remaining(gemini_pair_key(key_idx, model), _gemini_limit(model))


def gemini_remaining_total() -> int:
    models = [config.GEMINI_MODEL] + config.GEMINI_FALLBACK_MODELS
    return sum(
        gemini_pair_remaining(ki, m)
        for ki in range(len(config.GEMINI_API_KEYS) or 1)
        for m in models
    )


def gemini_model_remaining(model: str) -> int:
    return sum(
        gemini_pair_remaining(ki, model)
        for ki in range(len(config.GEMINI_API_KEYS) or 1)
    )


def summary() -> str:
    models = [config.GEMINI_MODEL] + config.GEMINI_FALLBACK_MODELS
    nkeys = len(config.GEMINI_API_KEYS) or 1
    parts = [f"{m.replace('gemini-', '')}: {gemini_model_remaining(m)} left ({nkeys} key{'s' if nkeys > 1 else ''})" for m in models]
    parts.append(f"IG: {remaining('instagram', config.IG_DAILY_LIMIT)}/day left")
    parts.append(f"FB: {remaining('facebook', config.FB_DAILY_LIMIT)}/day left")
    parts.append(f"X: {remaining('x', config.X_DAILY_LIMIT)}/day, {remaining('x_month', config.X_MONTHLY_LIMIT, 'month')}/month left")
    return " | ".join(parts)
