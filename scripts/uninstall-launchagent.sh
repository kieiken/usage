#!/bin/bash
set -euo pipefail

PLIST_NAME="com.lollapalooza.usage.plist"
TARGET_PLIST="${HOME}/Library/LaunchAgents/${PLIST_NAME}"
LEGACY_LABEL="com.lollapalooza.usag"
LEGACY_PLIST="${HOME}/Library/LaunchAgents/${LEGACY_LABEL}.plist"

echo "LaunchAgent をアンロードしています..."
launchctl unload "${TARGET_PLIST}" 2>/dev/null || true
if launchctl print "gui/$(id -u)/${LEGACY_LABEL}" >/dev/null 2>&1; then
    launchctl bootout "gui/$(id -u)/${LEGACY_LABEL}" 2>/dev/null || true
fi

echo "ファイルを削除しています..."
rm -f "${TARGET_PLIST}"
rm -f "${LEGACY_PLIST}"
rm -f "${HOME}/Library/Logs/usage/usage.log"
rm -f "${HOME}/Library/Logs/usage/usage.err.log"
rmdir "${HOME}/Library/Logs/usage" 2>/dev/null || true

echo "✓ 削除しました"
