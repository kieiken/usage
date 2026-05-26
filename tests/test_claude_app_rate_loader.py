"""Tests for ``claude_app_rate_loader``.

Per repo convention: never touch real ``~/.claude/``; patch path constants
with ``monkeypatch.setattr`` and use ``tmp_path``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import claude_app_rate_loader as rl
from history_loader import UsageEntry


def _entry(
    ts: datetime, *, input_: int = 0, output: int = 0, cc: int = 0, cr: int = 0
) -> UsageEntry:
    return UsageEntry(
        timestamp=ts,
        session_id="s",
        message_id="m",
        request_id="r",
        model="claude-sonnet-4-5",
        input_tokens=input_,
        output_tokens=output,
        cache_creation_tokens=cc,
        cache_read_tokens=cr,
        cost_usd=None,
        project="unit",
    )


# ---------------------------------------------------------------------------
# シナリオ1: 5h ローリング集計
# 前提: 5h 以内に2件 (input=100, output=50, cc=200, cr=1000)、5h 超過に1件
# とき: collect_window(now, 5h)
# ならば: 5h 以内2件のみ、cache_read*0.1 重みが適用
# ---------------------------------------------------------------------------
def test_collect_window_filters_by_rolling_5h() -> None:
    now = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
    entries = [
        # both in window
        _entry(now - timedelta(hours=1), input_=100, output=50, cc=200, cr=1000),
        _entry(now - timedelta(hours=4, minutes=59), input_=10, output=5, cc=20, cr=100),
        # out of window
        _entry(now - timedelta(hours=5, minutes=1), input_=999, output=999),
    ]
    total, oldest = rl.collect_window(now, rl.FIVE_HOUR, entries=entries)

    # (100+50+200+1000*0.1) + (10+5+20+100*0.1) = 450 + 45 = 495
    assert total == pytest.approx(495.0)
    assert oldest == now - timedelta(hours=4, minutes=59)


def test_collect_window_empty_returns_zero_and_none() -> None:
    now = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
    total, oldest = rl.collect_window(now, rl.FIVE_HOUR, entries=[])
    assert total == 0.0
    assert oldest is None


# ---------------------------------------------------------------------------
# シナリオ2: percentage 計算
# ---------------------------------------------------------------------------
def test_estimate_percent_basic() -> None:
    assert rl.estimate_percent(250_000, 1_000_000) == 25


def test_estimate_percent_clamps_to_100() -> None:
    assert rl.estimate_percent(5_000_000, 1_000_000) == 100


def test_estimate_percent_clamps_to_0() -> None:
    assert rl.estimate_percent(-100, 1_000_000) == 0


def test_estimate_percent_zero_budget_yields_0() -> None:
    assert rl.estimate_percent(123, 0) == 0


def test_estimate_percent_rounds_to_int() -> None:
    # 1234 / 1_000_000 * 100 = 0.1234 -> round = 0
    assert rl.estimate_percent(1234, 1_000_000) == 0
    # 5500 / 10000 * 100 = 55.0
    assert rl.estimate_percent(5500, 10000) == 55


# ---------------------------------------------------------------------------
# シナリオ3: derived ファイル生成
# ---------------------------------------------------------------------------
def test_build_derived_shape() -> None:
    now = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
    oldest = now - timedelta(hours=1)
    entries = [_entry(oldest, input_=500_000)]
    budgets = {"five_hour": 1_000_000, "seven_day": 10_000_000}

    data = rl.build_derived(now=now, entries=entries, budgets=budgets)

    rate = data["rate_limits"]
    assert rate["five_hour"]["used_percentage"] == 50
    assert rate["seven_day"]["used_percentage"] == 5
    assert rate["status"] == "estimated"
    assert data["_source"] == "claude_app_derived"
    assert data["_received_at_ts"] == now.timestamp()
    assert rate["five_hour"]["resets_at"] == (oldest + rl.FIVE_HOUR).timestamp()
    assert rate["seven_day"]["resets_at"] > now.timestamp()


def test_next_weekly_reset_at_uses_wednesday_2200_local_time() -> None:
    now = datetime(2026, 5, 26, 6, 22, 0, tzinfo=UTC)
    reset = datetime.fromtimestamp(rl._next_weekly_reset_at(now)).astimezone()

    assert reset.weekday() == rl.WEEKLY_RESET_WEEKDAY
    assert reset.hour == rl.WEEKLY_RESET_HOUR
    assert reset.minute == 0
    assert reset > now.astimezone()


def test_write_atomic_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "derived.json"
    payload = {"hello": "world"}
    rl.write_atomic(payload, target=target)

    assert target.exists()
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded == payload


def test_write_atomic_replaces_existing(tmp_path: Path) -> None:
    target = tmp_path / "derived.json"
    target.write_text('{"old": true}', encoding="utf-8")
    rl.write_atomic({"new": True}, target=target)
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}


# ---------------------------------------------------------------------------
# シナリオ5: プラン設定読み込み
# ---------------------------------------------------------------------------
def test_load_plan_config_default_when_missing(tmp_path: Path) -> None:
    cfg = rl._load_plan_config(path=tmp_path / "nope.json")
    assert cfg == rl.PLAN_BUDGETS[rl.DEFAULT_PLAN]


def test_load_plan_config_by_name(tmp_path: Path) -> None:
    p = tmp_path / "plan.json"
    p.write_text(json.dumps({"plan": "pro"}), encoding="utf-8")
    assert rl._load_plan_config(path=p) == rl.PLAN_BUDGETS["pro"]


def test_load_plan_config_explicit_budgets_win(tmp_path: Path) -> None:
    p = tmp_path / "plan.json"
    p.write_text(
        json.dumps({"plan": "pro", "budgets": {"five_hour": 9, "seven_day": 99}}),
        encoding="utf-8",
    )
    assert rl._load_plan_config(path=p) == {"five_hour": 9, "seven_day": 99}


def test_load_plan_config_invalid_budgets_falls_back(tmp_path: Path) -> None:
    p = tmp_path / "plan.json"
    # negative budgets are rejected; falls through to plan name -> default
    p.write_text(
        json.dumps({"budgets": {"five_hour": -1, "seven_day": -1}}),
        encoding="utf-8",
    )
    assert rl._load_plan_config(path=p) == rl.PLAN_BUDGETS[rl.DEFAULT_PLAN]


def test_load_plan_config_malformed_json_falls_back(tmp_path: Path) -> None:
    p = tmp_path / "plan.json"
    p.write_text("{not json", encoding="utf-8")
    assert rl._load_plan_config(path=p) == rl.PLAN_BUDGETS[rl.DEFAULT_PLAN]
