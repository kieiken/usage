"""Estimate Claude rate_limits when Claude.app is used instead of Claude Code CLI.

Background
----------
Claude.app (the desktop chat client) does not fire statusLine hooks, so the
canonical ``~/.claude/usage-status.json`` is never written. ``usage_client.py``
therefore has no live Session (5h) / Weekly (7d) percentages to display.

This module derives a *best-effort estimate* of those percentages from the
JSONL conversation logs under ``~/.claude/projects/`` and writes the result to
``~/.claude/usage-status-derived.json``. ``usage_client.py`` reads that file as
the **final** fallback, after the canonical hook output, the legacy
``usag-status.json``, and the ``tt-status.json`` interop file.

Method
------
1. ``history_loader.load_entries`` enumerates assistant ``UsageEntry`` rows.
2. Sum weighted tokens for the rolling 5h and 7d windows
   (``cache_read`` is counted at 0.1x to mirror Anthropic API discounts).
3. Divide by plan-specific budgets to obtain percentages.
4. Atomically write the derived status JSON.

Known limitations
-----------------
- Anthropic-side ``rate_limits`` are not exposed to Claude.app logs; this is an
  *estimate* and will drift from CLI's true values.
- claude.ai web usage is invisible here.
- Plan budgets below are unofficial heuristics and are deliberately
  overridable via ``~/.claude/usage-plan.json``.
- Phase 2 will add a calibration loop (``~/.claude/usage-calibration.json``):
  the user records actual vs estimated samples; a per-window EMA correction
  factor ``k`` is learned and applied on top of these raw estimates.

Run standalone::

    python3 claude_app_rate_loader.py            # write derived file
    USAGE_DEBUG=1 python3 claude_app_rate_loader.py   # also log to stderr
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from history_loader import UsageEntry, load_entries

DERIVED_STATUS_FILE = Path(os.path.expanduser("~/.claude/usage-status-derived.json"))
PLAN_CONFIG_FILE = Path(os.path.expanduser("~/.claude/usage-plan.json"))

# Token weighting for rate-limit estimation.
# ``cache_read`` is heavily discounted in API pricing; we assume the same in
# rate limits. This is calibratable later via usage-calibration.json (Phase 2).
TOKEN_WEIGHTS: dict[str, float] = {
    "input": 1.0,
    "output": 1.0,
    "cache_creation": 1.0,
    "cache_read": 0.1,
}

# Plan-specific token budgets (best-effort estimates; Anthropic does not
# publish these in tokens). 5x/20x multiplier of estimated Pro budgets.
# Override with ``~/.claude/usage-plan.json``: ``{"plan": "max_5x"}`` or
# ``{"budgets": {"five_hour": N, "seven_day": M}}``.
PLAN_BUDGETS: dict[str, dict[str, int]] = {
    "pro": {"five_hour": 200_000, "seven_day": 2_000_000},
    "max_5x": {"five_hour": 1_000_000, "seven_day": 10_000_000},
    "max_20x": {"five_hour": 4_000_000, "seven_day": 40_000_000},
}
DEFAULT_PLAN = "max_5x"

FIVE_HOUR = timedelta(hours=5)
SEVEN_DAY = timedelta(days=7)
WEEKLY_RESET_WEEKDAY = 2  # Python datetime weekday: Monday=0, Wednesday=2
WEEKLY_RESET_HOUR = 22


def _load_plan_config(path: Path = PLAN_CONFIG_FILE) -> dict[str, int]:
    """Return the budget dict to use. Falls back to ``PLAN_BUDGETS[DEFAULT_PLAN]``.

    Precedence in the JSON file:
        1. Explicit ``"budgets": {"five_hour": int, "seven_day": int}``
        2. ``"plan": "<pro|max_5x|max_20x>"``
        3. Anything else / unreadable file -> default plan
    """
    if not path.exists():
        return PLAN_BUDGETS[DEFAULT_PLAN]
    try:
        with path.open(encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError):
        return PLAN_BUDGETS[DEFAULT_PLAN]
    if not isinstance(cfg, dict):
        return PLAN_BUDGETS[DEFAULT_PLAN]

    budgets = cfg.get("budgets")
    if isinstance(budgets, dict):
        five = budgets.get("five_hour")
        seven = budgets.get("seven_day")
        if isinstance(five, int) and isinstance(seven, int) and five > 0 and seven > 0:
            return {"five_hour": five, "seven_day": seven}

    plan = cfg.get("plan")
    if isinstance(plan, str) and plan in PLAN_BUDGETS:
        return PLAN_BUDGETS[plan]

    return PLAN_BUDGETS[DEFAULT_PLAN]


def weighted_tokens(entry: UsageEntry) -> float:
    """Apply ``TOKEN_WEIGHTS`` to one ``UsageEntry``."""
    return (
        entry.input_tokens * TOKEN_WEIGHTS["input"]
        + entry.output_tokens * TOKEN_WEIGHTS["output"]
        + entry.cache_creation_tokens * TOKEN_WEIGHTS["cache_creation"]
        + entry.cache_read_tokens * TOKEN_WEIGHTS["cache_read"]
    )


def collect_window(
    now: datetime,
    window: timedelta,
    entries: list[UsageEntry] | None = None,
) -> tuple[float, datetime | None]:
    """Sum weighted tokens within ``now - window .. now``.

    Returns ``(weighted_token_sum, oldest_timestamp_in_window)``. The oldest
    timestamp is informational (currently unused by the writer) and may be
    used in Phase 2 to derive a more accurate ``resets_at``.

    If ``entries`` is omitted, ``history_loader.load_entries`` is called with
    ``hours_back`` slightly larger than the window to avoid edge-case filtering.
    """
    if entries is None:
        hours = max(1, int(window.total_seconds() / 3600) + 1)
        entries = load_entries(hours_back=hours)
    cutoff = now - window
    relevant = [e for e in entries if e.timestamp >= cutoff]
    if not relevant:
        return 0.0, None
    total = sum(weighted_tokens(e) for e in relevant)
    oldest = min(e.timestamp for e in relevant)
    return total, oldest


def estimate_percent(weighted: float, budget: int) -> int:
    """Clamp ``weighted / budget`` to ``[0, 100]`` and round to int."""
    if budget <= 0:
        return 0
    pct = (weighted / budget) * 100
    return max(0, min(100, round(pct)))


def _rolling_reset_at(now: datetime, window: timedelta, oldest: datetime | None) -> float:
    """Return the observable rolling-window reset time.

    For the 5h session limit, the next meaningful drop happens when the oldest
    in-window usage entry leaves the window, not simply ``now + 5h``.
    """
    if oldest is None:
        return (now + window).timestamp()
    candidate = oldest + window
    if candidate <= now:
        candidate = now
    return candidate.timestamp()


def _next_weekly_reset_at(now: datetime) -> float:
    """Return Claude's weekly reset boundary: next Wednesday at 22:00 local time."""
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


def build_derived(
    now: datetime | None = None,
    entries: list[UsageEntry] | None = None,
    budgets: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build the dict that mirrors the schema of ``usage-status.json``.

    Optional ``entries`` and ``budgets`` exist for test injection; production
    paths leave them ``None`` to defer to ``load_entries`` and the plan config.
    """
    if now is None:
        now = datetime.now(UTC)
    if budgets is None:
        budgets = _load_plan_config()
    if entries is None:
        # One load covers both windows: 7d superset is enough.
        entries = load_entries(hours_back=int(SEVEN_DAY.total_seconds() / 3600) + 1)

    five_tok, five_oldest = collect_window(now, FIVE_HOUR, entries=entries)
    seven_tok, _ = collect_window(now, SEVEN_DAY, entries=entries)
    five_pct = estimate_percent(five_tok, budgets["five_hour"])
    seven_pct = estimate_percent(seven_tok, budgets["seven_day"])

    # ``resets_at`` is a coarse approximation: Anthropic's true window start is
    # not directly exposed to Claude.app logs. For the 5h window, use the oldest
    # in-window usage entry as the next rolling boundary. The weekly boundary is
    # shown by Claude's usage screen as Wednesday 22:00 local time for Max plans.
    return {
        "rate_limits": {
            "five_hour": {
                "used_percentage": five_pct,
                "resets_at": _rolling_reset_at(now, FIVE_HOUR, five_oldest),
            },
            "seven_day": {
                "used_percentage": seven_pct,
                "resets_at": _next_weekly_reset_at(now),
            },
            "status": "estimated",
        },
        "_received_at": now.isoformat(),
        "_received_at_ts": now.timestamp(),
        "_source": "claude_app_derived",
        "_estimate_notes": {
            "five_hour_weighted_tokens": int(five_tok),
            "seven_day_weighted_tokens": int(seven_tok),
            "budgets_used": budgets,
            "weights": TOKEN_WEIGHTS,
        },
    }


def write_atomic(data: dict[str, Any], target: Path = DERIVED_STATUS_FILE) -> None:
    """Atomically write ``data`` as JSON to ``target`` (tmp file + rename)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    tmp_path: str | None = tmp_name
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp_name, str(target))
        tmp_path = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)


def main() -> int:
    try:
        data = build_derived()
        write_atomic(data)
    except Exception as exc:  # noqa: BLE001  -- standalone entry point
        if os.environ.get("USAGE_DEBUG") == "1":
            print(f"claude_app_rate_loader failed: {exc}", file=sys.stderr)
        return 1
    if os.environ.get("USAGE_DEBUG") == "1":
        rl = data["rate_limits"]
        print(
            f"derived: 5h={rl['five_hour']['used_percentage']}%, "
            f"7d={rl['seven_day']['used_percentage']}%",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
