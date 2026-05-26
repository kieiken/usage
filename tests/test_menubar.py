from __future__ import annotations

from datetime import UTC, datetime

import pytest

import history_loader
import menubar
from usage_client import PollOutcome, PollState, UsageSnapshot


def test_format_human_time_zero_and_negative() -> None:
    assert menubar.format_human_time(0) == "0m"
    assert menubar.format_human_time(-1) == "0m"


def test_format_human_time_sub_minute() -> None:
    assert menubar.format_human_time(30) == "0m"


def test_format_human_time_minutes_hours_and_days() -> None:
    assert menubar.format_human_time(90) == "1m"
    assert menubar.format_human_time(3700) == "1h 1m"
    assert menubar.format_human_time(90000) == "1d 1h"


def test_format_percent() -> None:
    assert menubar._format_percent(50.0) == "50"
    assert menubar._format_percent(50.5) == "50.5"
    assert menubar._format_percent(0.0) == "0"


def test_bar_color_thresholds() -> None:
    brand = (0.1, 0.2, 0.3)

    assert menubar._bar_color(80, brand) == menubar.DANGER_COLOR
    assert menubar._bar_color(60, brand) == menubar.WARN_COLOR
    assert menubar._bar_color(49, brand) == brand


def test_quota_row_returns_missing_when_percent_is_none() -> None:
    row = menubar._quota_row("Session", None, 1_100.0, 1_000.0, menubar.CODEX_COLOR)

    assert row.available is False
    assert row.percent is None
    assert row.percent_text == "--"


def test_quota_row_returns_missing_when_reset_is_none() -> None:
    row = menubar._quota_row("Session", 50.0, None, 1_000.0, menubar.CODEX_COLOR)

    assert row.available is False
    assert row.percent is None
    assert row.percent_text == "--"


def test_quota_row_formats_available_row() -> None:
    row = menubar._quota_row(
        "Session", 50.5, 1_090.0, 1_000.0, menubar.CODEX_COLOR, language="zh-TW"
    )

    assert row.available is True
    assert row.percent == 50.5
    assert row.percent_text == "50.5% 已用"
    assert row.reset_text.startswith("重置 ")
    assert row.warning is False
    assert row.color == menubar.WARN_COLOR


def test_quota_row_clamps_percent_to_range() -> None:
    high = menubar._quota_row(
        "Session", 150.0, 1_090.0, 1_000.0, menubar.CODEX_COLOR, language="zh-TW"
    )
    low = menubar._quota_row(
        "Session", -10.0, 1_090.0, 1_000.0, menubar.CODEX_COLOR, language="zh-TW"
    )

    assert high.percent == 100.0
    assert high.percent_text == "100% 已用"
    assert low.percent == 0.0
    assert low.percent_text == "0% 已用"


def test_missing_row() -> None:
    row = menubar._missing_row("Weekly", menubar.CLAUDE_COLOR, language="zh-TW")

    assert row.available is False
    assert row.percent is None
    assert row.percent_text == "--"
    assert row.reset_text == "重置 --"
    assert row.warning is False


def test_quota_row_uses_burn_warning_when_forecast_exceeds_risk_threshold() -> None:
    row = menubar._quota_row(
        "Session",
        82.0,
        1_000.0 + (51 * 60),
        1_000.0,
        menubar.CODEX_COLOR,
        language="zh-TW",
        forecast_seconds=18 * 60,
    )

    assert row.warning is True
    assert row.reset_text == "⚠ 剩 18分鐘 用完(重置還要 51分鐘)"


def test_quota_row_keeps_reset_text_when_forecast_is_not_before_reset() -> None:
    row = menubar._quota_row(
        "Session",
        82.0,
        1_000.0 + (18 * 60),
        1_000.0,
        menubar.CODEX_COLOR,
        language="zh-TW",
        forecast_seconds=51 * 60,
    )

    assert row.warning is False
    assert row.reset_text == "重置 18分鐘"


def test_quota_row_keeps_reset_text_when_percent_is_below_warning_floor() -> None:
    row = menubar._quota_row(
        "Session",
        30.0,
        1_000.0 + (51 * 60),
        1_000.0,
        menubar.CODEX_COLOR,
        language="zh-TW",
        forecast_seconds=18 * 60,
    )

    assert row.warning is False
    assert row.reset_text == "重置 51分鐘"


def test_today_title_mock() -> None:
    assert menubar._today_title(mock=True, language="zh-TW") == "今日：$45.20 (50,193,442 tokens)"


def test_today_title_returns_zero_fallback_when_loaders_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        menubar,
        "load_entries",
        lambda *, hours_back=24: (_ for _ in ()).throw(OSError),
    )

    assert menubar._today_title(mock=False, language="zh-TW") == "今日：$0.00 (0 tokens)"


def test_empty_state() -> None:
    state = menubar._empty_state()
    rows = (
        state.claude_session,
        state.claude_weekly,
        state.codex_session,
        state.codex_weekly,
    )

    assert all(row.available is False for row in rows)
    assert state.projects == []
    assert state.projects_7d == []
    assert state.projects_30d == []
    assert state.show_install_button is False


def test_error_state_uses_message_and_mock_today_title() -> None:
    state = menubar._error_state("boom", mock=True, language="zh-TW")

    assert "boom" in state.status_text
    assert state.today_text == "今日：$45.20 (50,193,442 tokens)"


def test_popover_size_has_positive_dimensions() -> None:
    size = menubar._popover_size(menubar._empty_state())

    assert size.width > 0
    assert size.height > 0


def test_project_rows_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    delegate = menubar.AppDelegate.alloc().initWithMock_interval_(False, 60)
    monkeypatch.setattr(menubar, "load_entries", lambda *, hours_back=24: [])

    assert delegate._project_rows(hours_back=24) == []


def test_project_rows_top3(monkeypatch: pytest.MonkeyPatch) -> None:
    delegate = menubar.AppDelegate.alloc().initWithMock_interval_(False, 60)

    entries = [
        history_loader.UsageEntry(
            timestamp=datetime(2026, 5, 21, tzinfo=UTC),
            session_id="s1",
            message_id="m1",
            request_id="r1",
            model="claude",
            input_tokens=4_000_000,
            output_tokens=1_000_000,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            cost_usd=2.0,
            project="usage",
        ),
        history_loader.UsageEntry(
            timestamp=datetime(2026, 5, 21, tzinfo=UTC),
            session_id="s2",
            message_id="m2",
            request_id="r2",
            model="claude",
            input_tokens=2_000_000,
            output_tokens=500_000,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            cost_usd=1.0,
            project="FinMind",
        ),
        history_loader.UsageEntry(
            timestamp=datetime(2026, 5, 21, tzinfo=UTC),
            session_id="s3",
            message_id="m3",
            request_id="r3",
            model="claude",
            input_tokens=1_000_000,
            output_tokens=300_000,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            cost_usd=0.5,
            project="AI客服",
        ),
        history_loader.UsageEntry(
            timestamp=datetime(2026, 5, 21, tzinfo=UTC),
            session_id="s4",
            message_id="m4",
            request_id="r4",
            model="claude",
            input_tokens=600_000,
            output_tokens=100_000,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            cost_usd=0.2,
            project="sidecar",
        ),
        history_loader.UsageEntry(
            timestamp=datetime(2026, 5, 21, tzinfo=UTC),
            session_id="s5",
            message_id="m5",
            request_id="r5",
            model="claude",
            input_tokens=500_000,
            output_tokens=100_000,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            cost_usd=None,
            project="ops",
        ),
    ]

    monkeypatch.setattr(menubar, "load_entries", lambda *, hours_back=24: entries)

    rows = delegate._project_rows(hours_back=24)

    assert len(rows) == 3
    assert rows[0] == ("usage", 5_000_000, 2.0)
    assert rows[1][0] == "FinMind"
    assert rows[2][0] == "AI客服"


def test_project_rows_7d_mock() -> None:
    delegate = menubar.AppDelegate.alloc().initWithMock_interval_(True, 60)

    rows = delegate._project_rows(hours_back=168)

    assert len(rows) == 3
    assert rows[0][1] == 78_400_000


def test_project_rows_30d_mock() -> None:
    delegate = menubar.AppDelegate.alloc().initWithMock_interval_(True, 60)

    rows = delegate._project_rows(hours_back=720)

    assert len(rows) == 3
    assert rows[0][1] == 312_000_000


def test_state_from_outcome_replaces_claude_reset_with_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delegate = menubar.AppDelegate.alloc().initWithMock_interval_(False, 60)
    delegate.language = "zh-TW"
    monkeypatch.setattr("time.time", lambda: 1_600.0)
    delegate.burn_rate_trackers["claude_session"].record(1_000.0, 72.0)
    delegate.burn_rate_trackers["claude_session"].record(1_150.0, 74.5)
    delegate.burn_rate_trackers["claude_session"].record(1_300.0, 77.0)
    delegate.burn_rate_trackers["claude_session"].record(1_450.0, 79.5)
    delegate.burn_rate_trackers["claude_session"].record(1_600.0, 82.0)

    outcome = PollOutcome(
        state=PollState.SUCCESS,
        snapshot=UsageSnapshot(
            current_percent=82,
            current_reset_at=1_600.0 + (51 * 60),
            weekly_percent=20,
            weekly_reset_at=1_600.0 + (2 * 86400),
            current_status="ok",
            polled_at=1_600.0,
        ),
    )

    state = delegate._state_from_outcome(outcome, delegate._codex_rows()[0], [], [], [])

    assert state.claude_session.warning is True
    assert state.claude_session.reset_text == "⚠ 剩 18分鐘 用完(重置還要 51分鐘)"


def test_state_from_outcome_keeps_reset_when_burn_rate_is_not_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delegate = menubar.AppDelegate.alloc().initWithMock_interval_(False, 60)
    delegate.language = "zh-TW"
    monkeypatch.setattr("time.time", lambda: 1_600.0)
    delegate.burn_rate_trackers["claude_session"].record(1_000.0, 82.0)
    delegate.burn_rate_trackers["claude_session"].record(1_150.0, 79.0)
    delegate.burn_rate_trackers["claude_session"].record(1_300.0, 76.0)
    delegate.burn_rate_trackers["claude_session"].record(1_450.0, 73.0)
    delegate.burn_rate_trackers["claude_session"].record(1_600.0, 70.0)

    outcome = PollOutcome(
        state=PollState.SUCCESS,
        snapshot=UsageSnapshot(
            current_percent=70,
            current_reset_at=1_600.0 + (51 * 60),
            weekly_percent=20,
            weekly_reset_at=1_600.0 + (2 * 86400),
            current_status="ok",
            polled_at=1_600.0,
        ),
    )

    state = delegate._state_from_outcome(outcome, delegate._codex_rows()[0], [], [], [])

    assert state.claude_session.warning is False
    assert state.claude_session.reset_text == "重置 51分鐘"
