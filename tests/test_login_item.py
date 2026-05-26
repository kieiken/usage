from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

import login_item


def test_build_plist_for_app_context() -> None:
    plist_text = login_item.build_plist(
        ["/usr/bin/open", "/Applications/usage.app"],
        None,
    )

    payload = plistlib.loads(plist_text.encode("utf-8"))

    assert payload["Label"] == login_item.LABEL
    assert payload["RunAtLoad"] is True
    assert payload["ProgramArguments"] == ["/usr/bin/open", "/Applications/usage.app"]
    assert "KeepAlive" not in payload
    assert "WorkingDirectory" not in payload
    assert payload["StandardOutPath"].endswith("/Library/Logs/usage/usage.log")
    assert payload["StandardErrorPath"].endswith("/Library/Logs/usage/usage.err.log")


def test_build_plist_for_source_context() -> None:
    plist_text = login_item.build_plist(
        ["/usr/bin/python3", "/tmp/usage/main.py"],
        "/tmp/usage",
    )

    payload = plistlib.loads(plist_text.encode("utf-8"))

    assert payload["ProgramArguments"] == ["/usr/bin/python3", "/tmp/usage/main.py"]
    assert payload["WorkingDirectory"] == "/tmp/usage"
    assert payload["KeepAlive"] == {"SuccessfulExit": False}


def test_is_enabled_uses_plist_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plist_path = tmp_path / "com.lollapalooza.usage.plist"
    monkeypatch.setattr(login_item, "PLIST_PATH", plist_path)

    assert login_item.is_enabled() is False

    plist_path.write_text("plist", encoding="utf-8")

    assert login_item.is_enabled() is True


def test_disable_removes_plist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plist_path = tmp_path / "com.lollapalooza.usage.plist"
    plist_path.write_text("plist", encoding="utf-8")
    monkeypatch.setattr(login_item, "PLIST_PATH", plist_path)

    login_item.disable()

    assert plist_path.exists() is False
    assert login_item.is_enabled() is False
