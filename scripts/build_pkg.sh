#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${PROJECT_DIR}/dist"
APP_PATH="${DIST_DIR}/usage.app"
DERIVER_SOURCE="${PROJECT_DIR}/scripts/usage-claude-desktop-deriver.py"
PKG_ROOT="${DIST_DIR}/pkg-root"
PKG_SCRIPTS="${DIST_DIR}/pkg-scripts"
COMPONENT_PKG="${DIST_DIR}/usage-component.pkg"
FINAL_PKG="${DIST_DIR}/usage-installer.pkg"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "dist/usage.app が見つかりません。先に ./scripts/build_app.sh を実行してください。" >&2
  exit 1
fi

if [[ ! -f "${DERIVER_SOURCE}" ]]; then
  echo "${DERIVER_SOURCE} が見つかりません。" >&2
  exit 1
fi

rm -rf "${PKG_ROOT}" "${PKG_SCRIPTS}" "${COMPONENT_PKG}" "${FINAL_PKG}"
export COPYFILE_DISABLE=1
mkdir -p \
  "${PKG_ROOT}/Applications" \
  "${PKG_ROOT}/Library/Application Support/usage" \
  "${PKG_SCRIPTS}"

ditto --norsrc "${APP_PATH}" "${PKG_ROOT}/Applications/usage.app"
install -m 755 "${DERIVER_SOURCE}" \
  "${PKG_ROOT}/Library/Application Support/usage/usage-claude-desktop-deriver.py"
find "${PKG_ROOT}" -name '._*' -delete

cat > "${PKG_SCRIPTS}/postinstall" <<'POSTINSTALL'
#!/usr/bin/env bash
set -euo pipefail

LABEL="com.lollapalooza.usage.deriver"
DERIVER_PATH="/Library/Application Support/usage/usage-claude-desktop-deriver.py"
LOG_DIR="/Library/Logs/usage"

console_user="$(stat -f %Su /dev/console || true)"
if [[ -z "${console_user}" || "${console_user}" == "root" || "${console_user}" == "loginwindow" ]]; then
  echo "ログイン中のユーザーを特定できなかったため、アプリのみインストールしました。"
  exit 0
fi

user_home="$(dscl . -read "/Users/${console_user}" NFSHomeDirectory | awk '{print $2}')"
if [[ -z "${user_home}" || ! -d "${user_home}" ]]; then
  echo "${console_user} のホームディレクトリを特定できませんでした。"
  exit 0
fi

uid="$(id -u "${console_user}")"
launch_agents="${user_home}/Library/LaunchAgents"
plist_path="${launch_agents}/${LABEL}.plist"

mkdir -p "${launch_agents}" "${LOG_DIR}"
chown "${console_user}" "${launch_agents}"
chmod 755 "${launch_agents}"
chmod 755 "${DERIVER_PATH}"

cat > "${plist_path}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>${DERIVER_PATH}</string>
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

chown "${console_user}" "${plist_path}"
chmod 644 "${plist_path}"

launchctl bootout "gui/${uid}/${LABEL}" 2>/dev/null || true
launchctl asuser "${uid}" launchctl bootstrap "gui/${uid}" "${plist_path}" 2>/dev/null || true
launchctl asuser "${uid}" launchctl kickstart -k "gui/${uid}/${LABEL}" 2>/dev/null || true

exit 0
POSTINSTALL

chmod 755 "${PKG_SCRIPTS}/postinstall"

pkgbuild \
  --root "${PKG_ROOT}" \
  --scripts "${PKG_SCRIPTS}" \
  --identifier "com.lollapalooza.usage.pkg" \
  --version "0.9.1" \
  --install-location "/" \
  "${COMPONENT_PKG}"

productbuild \
  --package "${COMPONENT_PKG}" \
  "${FINAL_PKG}"

rm -rf "${PKG_ROOT}" "${PKG_SCRIPTS}" "${COMPONENT_PKG}"

echo "作成しました: ${FINAL_PKG}"
