#!/usr/bin/env bash
set -euo pipefail

REPO="${USAGE_REPO:-aqua5230/usage}"
REF="${USAGE_REF:-main}"
APP_NAME="usage.app"
INSTALL_DIR="${USAGE_INSTALL_DIR:-/Applications}"
APP_PATH="${INSTALL_DIR}/${APP_NAME}"
RAW_BASE="${USAGE_RAW_BASE:-https://raw.githubusercontent.com/${REPO}/${REF}}"
ZIP_URL="${USAGE_ZIP_URL:-https://github.com/${REPO}/releases/latest/download/usage.app.zip}"
DERIVER_URL="${USAGE_DERIVER_URL:-https://github.com/${REPO}/releases/latest/download/usage-claude-desktop-deriver.py}"
INSTALL_DERIVER_URL="${USAGE_INSTALL_DERIVER_URL:-https://github.com/${REPO}/releases/latest/download/install-desktop-deriver.sh}"

tmp="$(mktemp -d)"
cleanup() {
  rm -rf "${tmp}"
}
trap cleanup EXIT

echo "usage.app をダウンロードしています: ${ZIP_URL}"
curl -fL "${ZIP_URL}" -o "${tmp}/usage.app.zip"
unzip -q "${tmp}/usage.app.zip" -d "${tmp}"

if [[ ! -d "${tmp}/${APP_NAME}" ]]; then
  echo "Release zip に ${APP_NAME} が含まれていません" >&2
  exit 1
fi

if [[ -d "${APP_PATH}" ]]; then
  backup="${APP_PATH}.backup.$(date +%Y%m%d%H%M%S)"
  echo "既存の app をバックアップします: ${backup}"
  mv "${APP_PATH}" "${backup}"
fi

echo "${APP_PATH} にインストールしています"
ditto "${tmp}/${APP_NAME}" "${APP_PATH}"
xattr -dr com.apple.quarantine "${APP_PATH}" 2>/dev/null || true

echo "Claude Desktop 使用量推算 LaunchAgent をインストールしています"
mkdir -p "${tmp}/scripts"
curl -fL "${DERIVER_URL}" -o "${tmp}/scripts/usage-claude-desktop-deriver.py" \
  || curl -fL "${RAW_BASE}/scripts/usage-claude-desktop-deriver.py" \
    -o "${tmp}/scripts/usage-claude-desktop-deriver.py"
curl -fL "${INSTALL_DERIVER_URL}" -o "${tmp}/scripts/install-desktop-deriver.sh" \
  || curl -fL "${RAW_BASE}/scripts/install-desktop-deriver.sh" \
    -o "${tmp}/scripts/install-desktop-deriver.sh"
chmod +x "${tmp}/scripts/install-desktop-deriver.sh"
bash "${tmp}/scripts/install-desktop-deriver.sh"

echo "${APP_NAME} を起動しています"
open -a "${APP_PATH}"

echo "完了しました。"
