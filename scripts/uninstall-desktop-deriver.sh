#!/usr/bin/env bash
set -euo pipefail

LABEL="com.lollapalooza.usage.deriver"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
SCRIPT_PATH="${HOME}/Library/Application Support/usage/usage-claude-desktop-deriver.py"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "${PLIST_PATH}" "${SCRIPT_PATH}"

echo "${LABEL} を削除しました"
