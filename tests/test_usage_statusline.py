from __future__ import annotations

import io
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

import usage_statusline


def test_save_writes_status_json_with_received_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    status_file = tmp_path / "usage-status.json"
    now = datetime(2026, 1, 1, 12, 30, tzinfo=UTC)
    monkeypatch.setattr(usage_statusline, "STATUS_FILE", str(status_file))

    usage_statusline.save({"rate_limits": {"status": "ok"}}, now)

    data = json.loads(status_file.read_text(encoding="utf-8"))
    assert data["rate_limits"] == {"status": "ok"}
    assert data["_received_at"] == now.isoformat()
    assert data["_received_at_ts"] == now.timestamp()


def test_save_cleans_temp_file_when_atomic_replace_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    status_file = tmp_path / "usage-status.json"
    monkeypatch.setattr(usage_statusline, "STATUS_FILE", str(status_file))

    def fail_replace(src: str, dst: str) -> None:
        _ = src, dst
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        usage_statusline.save({"ok": True}, datetime(2026, 1, 1, tzinfo=UTC))

    assert not status_file.exists()
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize("stdin_text", ["", "   \n", "{bad json", "[1, 2, 3]"])
def test_main_ignores_invalid_or_empty_stdin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stdin_text: str,
) -> None:
    status_file = tmp_path / "usage-status.json"
    monkeypatch.setattr(usage_statusline, "STATUS_FILE", str(status_file))
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))

    usage_statusline.main()

    assert not status_file.exists()


def test_main_writes_valid_json_object(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    status_file = tmp_path / "usage-status.json"
    monkeypatch.setattr(usage_statusline, "STATUS_FILE", str(status_file))
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"rate_limits": {"status": "ok"}}'))

    usage_statusline.main()

    data = json.loads(status_file.read_text(encoding="utf-8"))
    assert data["rate_limits"] == {"status": "ok"}
    assert isinstance(data["_received_at"], str)
    assert isinstance(data["_received_at_ts"], int | float)


def test_main_returns_when_stdin_read_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class BrokenStdin:
        def read(self) -> str:
            raise RuntimeError("read failed")

    status_file = tmp_path / "usage-status.json"
    monkeypatch.setattr(usage_statusline, "STATUS_FILE", str(status_file))
    monkeypatch.setattr(sys, "stdin", BrokenStdin())

    usage_statusline.main()

    assert not status_file.exists()


def test_main_logs_invalid_json_in_debug_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status_file = tmp_path / "usage-status.json"
    monkeypatch.setattr(usage_statusline, "STATUS_FILE", str(status_file))
    monkeypatch.setattr(sys, "stdin", io.StringIO("{bad json"))
    monkeypatch.setenv("USAGE_DEBUG", "1")

    usage_statusline.main()

    captured = capsys.readouterr()
    assert "usage_statusline: invalid stdin JSON" in captured.err
    assert not status_file.exists()
