#!/usr/bin/env python3
"""Write ~/.claude/usage-status-derived.json from local Claude Desktop logs.

This standalone script intentionally uses only Python 3.9-compatible standard
library features so a GitHub release installer can run it with /usr/bin/python3.
It mirrors claude_app_rate_loader.py closely, but avoids importing project
modules from the app bundle.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

CLAUDE_PROJECTS_DIR = Path(os.path.expanduser("~/.claude/projects"))
DERIVED_STATUS_FILE = Path(os.path.expanduser("~/.claude/usage-status-derived.json"))

FIVE_HOUR = timedelta(hours=5)
SEVEN_DAY = timedelta(days=7)
WEEKLY_RESET_WEEKDAY = 2
WEEKLY_RESET_HOUR = 22

TOKEN_WEIGHTS = {
    "input": 1.0,
    "output": 1.0,
    "cache_creation": 1.0,
    "cache_read": 0.1,
}

DEFAULT_BUDGETS = {
    "five_hour": 1_000_000,
    "seven_day": 10_000_000,
}


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _as_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, value)


def _load_entries(hours_back: int) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    if not CLAUDE_PROJECTS_DIR.is_dir():
        return entries

    cutoff_ts = cutoff.timestamp()
    for jsonl_path in CLAUDE_PROJECTS_DIR.rglob("*.jsonl"):
        try:
            if jsonl_path.stat().st_mtime < cutoff_ts:
                continue
        except OSError:
            continue
        _load_file(jsonl_path, cutoff, seen, entries)

    entries.sort(key=lambda entry: entry["timestamp"])
    return entries


def _load_file(
    path: Path,
    cutoff: datetime,
    seen: set[str],
    entries: list[dict[str, Any]],
) -> None:
    try:
        with path.open(encoding="utf-8") as file:
            for line in file:
                entry = _parse_line(line)
                if entry is None or entry["timestamp"] < cutoff:
                    continue
                key = entry["dedup_key"]
                if key in seen:
                    continue
                seen.add(key)
                entries.append(entry)
    except OSError:
        return


def _parse_line(line: str) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("type") != "assistant":
        return None

    message = data.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None

    timestamp = _parse_timestamp(data.get("timestamp"))
    if timestamp is None:
        return None

    input_tokens = _as_int(usage.get("input_tokens"))
    output_tokens = _as_int(usage.get("output_tokens"))
    cache_creation = _as_int(usage.get("cache_creation_input_tokens"))
    cache_read = _as_int(usage.get("cache_read_input_tokens"))
    if input_tokens + output_tokens + cache_creation + cache_read == 0:
        return None

    message_id = message.get("id") if isinstance(message.get("id"), str) else ""
    request_id = data.get("requestId") if isinstance(data.get("requestId"), str) else ""
    session_id = data.get("sessionId") if isinstance(data.get("sessionId"), str) else ""
    model = message.get("model") if isinstance(message.get("model"), str) else "unknown"

    if message_id or request_id:
        dedup_key = f"message:{message_id}:{request_id}"
    else:
        dedup_key = (
            f"entry:{session_id}:{timestamp.isoformat()}:{model}:"
            f"{input_tokens}:{output_tokens}:{cache_creation}:{cache_read}"
        )

    return {
        "timestamp": timestamp,
        "input": input_tokens,
        "output": output_tokens,
        "cache_creation": cache_creation,
        "cache_read": cache_read,
        "dedup_key": dedup_key,
    }


def _weighted_tokens(entry: dict[str, Any]) -> float:
    return float(
        entry["input"] * TOKEN_WEIGHTS["input"]
        + entry["output"] * TOKEN_WEIGHTS["output"]
        + entry["cache_creation"] * TOKEN_WEIGHTS["cache_creation"]
        + entry["cache_read"] * TOKEN_WEIGHTS["cache_read"]
    )


def _collect_window(
    now: datetime,
    window: timedelta,
    entries: list[dict[str, Any]],
) -> tuple[float, Optional[datetime]]:
    cutoff = now - window
    relevant = [entry for entry in entries if entry["timestamp"] >= cutoff]
    if not relevant:
        return 0.0, None
    total = sum(_weighted_tokens(entry) for entry in relevant)
    oldest = min(entry["timestamp"] for entry in relevant)
    return total, oldest


def _estimate_percent(weighted: float, budget: int) -> int:
    if budget <= 0 or not math.isfinite(weighted):
        return 0
    return max(0, min(100, round((weighted / budget) * 100)))


def _rolling_reset_at(now: datetime, window: timedelta, oldest: Optional[datetime]) -> float:
    if oldest is None:
        return (now + window).timestamp()
    candidate = oldest + window
    if candidate <= now:
        candidate = now
    return candidate.timestamp()


def _next_weekly_reset_at(now: datetime) -> float:
    local_now = now.astimezone()
    days_ahead = (WEEKLY_RESET_WEEKDAY - local_now.weekday()) % 7
    candidate = local_now.replace(
        hour=WEEKLY_RESET_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    ) + timedelta(days=days_ahead)
    if candidate <= local_now:
        candidate += SEVEN_DAY
    return candidate.timestamp()


def build_derived(now: Optional[datetime] = None) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)
    entries = _load_entries(hours_back=int(SEVEN_DAY.total_seconds() / 3600) + 1)
    five_tokens, five_oldest = _collect_window(now, FIVE_HOUR, entries)
    seven_tokens, _ = _collect_window(now, SEVEN_DAY, entries)

    return {
        "rate_limits": {
            "five_hour": {
                "used_percentage": _estimate_percent(
                    five_tokens,
                    DEFAULT_BUDGETS["five_hour"],
                ),
                "resets_at": _rolling_reset_at(now, FIVE_HOUR, five_oldest),
            },
            "seven_day": {
                "used_percentage": _estimate_percent(
                    seven_tokens,
                    DEFAULT_BUDGETS["seven_day"],
                ),
                "resets_at": _next_weekly_reset_at(now),
            },
            "status": "estimated",
        },
        "_received_at": now.isoformat(),
        "_received_at_ts": now.timestamp(),
        "_source": "claude_app_derived",
        "_estimate_notes": {
            "five_hour_weighted_tokens": int(five_tokens),
            "seven_day_weighted_tokens": int(seven_tokens),
            "budgets_used": DEFAULT_BUDGETS,
            "weights": TOKEN_WEIGHTS,
        },
    }


def write_atomic(data: dict[str, Any], target: Path = DERIVED_STATUS_FILE) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    tmp_path: Optional[str] = tmp_name
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False)
        os.replace(tmp_name, str(target))
        tmp_path = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)


def main() -> int:
    data = build_derived()
    write_atomic(data)
    if os.environ.get("USAGE_DEBUG") == "1":
        rate = data["rate_limits"]
        print(
            f"derived: 5h={rate['five_hour']['used_percentage']}%, "
            f"7d={rate['seven_day']['used_percentage']}%",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
