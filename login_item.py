from __future__ import annotations

import plistlib
import sys
from pathlib import Path
from typing import Any

from Foundation import NSBundle

LABEL = "com.lollapalooza.usage"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
_LOG_DIR = Path.home() / "Library" / "Logs" / "usage"


def build_plist(program_args: list[str], working_dir: str | None) -> str:
    log_dir = str(_LOG_DIR)
    payload: dict[str, object] = {
        "Label": LABEL,
        "RunAtLoad": True,
        "ProgramArguments": program_args,
        "EnvironmentVariables": {"USAGE_LANG": "ja"},
        "StandardOutPath": f"{log_dir}/usage.log",
        "StandardErrorPath": f"{log_dir}/usage.err.log",
        "ThrottleInterval": 15,
        "StartDelay": 10,
        "ProcessType": "Interactive",
    }
    if working_dir is None:
        # .app launchd entry uses `open <bundle>`; KeepAlive would re-open endlessly.
        pass
    else:
        payload["KeepAlive"] = {"SuccessfulExit": False}
        payload["WorkingDirectory"] = working_dir
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False).decode("utf-8")


def _bundle_value(bundle: Any, attr_name: str) -> str | None:
    attr = getattr(bundle, attr_name, None)
    value = attr() if callable(attr) else attr
    return str(value) if value is not None else None


def _program_context() -> tuple[list[str], str | None]:
    bundle = NSBundle.mainBundle()
    if _bundle_value(bundle, "bundleIdentifier") == LABEL:
        bundle_path = _bundle_value(bundle, "bundlePath")
        if bundle_path:
            return ["/usr/bin/open", bundle_path], None
    project_dir = Path(__file__).resolve().parent
    main_py = project_dir / "main.py"
    return [sys.executable, str(main_py)], str(project_dir)


def is_enabled() -> bool:
    return PLIST_PATH.exists()


def _plist_text() -> str:
    program_args, working_dir = _program_context()
    return build_plist(program_args, working_dir)


def _ensure_parent_dirs() -> None:
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def _write_plist(contents: str) -> None:
    PLIST_PATH.write_text(contents, encoding="utf-8")


def enable() -> None:
    _ensure_parent_dirs()
    _write_plist(_plist_text())


def _remove_plist() -> None:
    PLIST_PATH.unlink(missing_ok=True)


def disable() -> None:
    _remove_plist()
