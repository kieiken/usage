#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python3"
PLIST_NAME="com.lollapalooza.usage.plist"
TARGET_PLIST="${HOME}/Library/LaunchAgents/${PLIST_NAME}"
LEGACY_LABEL="com.lollapalooza.usag"
LEGACY_PLIST="${HOME}/Library/LaunchAgents/${LEGACY_LABEL}.plist"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "エラー: 仮想環境の Python が見つかりません ($VENV_PYTHON)"
    exit 1
fi

if launchctl print "gui/$(id -u)/${LEGACY_LABEL}" >/dev/null 2>&1; then
    launchctl bootout "gui/$(id -u)/${LEGACY_LABEL}" 2>/dev/null || true
fi
rm -f "${LEGACY_PLIST}"

mkdir -p "${HOME}/Library/Logs/usage"

echo "設定ファイルを生成しています..."
sed -e "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
    -e "s|__VENV_PYTHON__|${VENV_PYTHON}|g" \
    -e "s|__HOME__|${HOME}|g" \
    "${SCRIPT_DIR}/${PLIST_NAME}" > "${TARGET_PLIST}"

echo "LaunchAgent を読み込んでいます..."
launchctl unload "${TARGET_PLIST}" 2>/dev/null || true
launchctl load "${TARGET_PLIST}"

echo "ℹ 旧 ${LEGACY_LABEL} LaunchAgent があれば削除しました"
echo "✓ インストールしました。次回ログイン時に自動起動します。手動テスト: launchctl start com.lollapalooza.usage"
