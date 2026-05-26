#!/usr/bin/env bash
set -euo pipefail

LABEL="com.lollapalooza.usage.deriver"
SUPPORT_DIR="${HOME}/Library/Application Support/usage"
SCRIPT_PATH="${SUPPORT_DIR}/usage-claude-desktop-deriver.py"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="${HOME}/Library/Logs/usage"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_SCRIPT="${SCRIPT_DIR}/usage-claude-desktop-deriver.py"

if [[ ! -f "${SOURCE_SCRIPT}" ]]; then
  echo "${SOURCE_SCRIPT} が見つかりません" >&2
  exit 1
fi

mkdir -p "${SUPPORT_DIR}" "${LOG_DIR}" "${HOME}/Library/LaunchAgents"
cp "${SOURCE_SCRIPT}" "${SCRIPT_PATH}"
chmod 755 "${SCRIPT_PATH}"

cat > "${PLIST_PATH}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>${SCRIPT_PATH}</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>USAGE_DEBUG</key>
    <string>1</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>60</integer>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/deriver.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/deriver.err.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
launchctl kickstart -k "gui/$(id -u)/${LABEL}" 2>/dev/null || true

echo "${LABEL} をインストールしました"
echo "ステータスファイル: ${HOME}/.claude/usage-status-derived.json"
