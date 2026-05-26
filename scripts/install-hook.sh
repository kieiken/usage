#!/usr/bin/env bash
# usage の Claude Code statusLine hook をインストールする。
# usage.app だけをダウンロードし、ソースコードを持っていない利用者向け:
#   bash <(curl -fsSL https://raw.githubusercontent.com/aqua5230/usage/main/scripts/install-hook.sh)
#
# 処理内容:
#   1. usage_statusline.py を ~/.claude/usage-statusline.py にダウンロードする
#   2. ~/.claude/settings.json の statusLine をこの hook に向ける
#   3. 既存の statusLine があれば settings.usage.previousStatusLine に退避する
set -euo pipefail

REPO_RAW="https://raw.githubusercontent.com/aqua5230/usage/main"
CLAUDE_DIR="${HOME}/.claude"
HOOK_PATH="${CLAUDE_DIR}/usage-statusline.py"
SETTINGS_PATH="${CLAUDE_DIR}/settings.json"

mkdir -p "${CLAUDE_DIR}"

echo "↓ hook スクリプトを ${HOOK_PATH} にダウンロードしています"
curl -fsSL "${REPO_RAW}/usage_statusline.py" -o "${HOOK_PATH}"
chmod +x "${HOOK_PATH}"

PYTHON_BIN="$(command -v python3 || echo /usr/bin/python3)"

echo "✎ ${SETTINGS_PATH} を更新しています"
HOOK_PATH="${HOOK_PATH}" SETTINGS_PATH="${SETTINGS_PATH}" PYTHON_BIN="${PYTHON_BIN}" \
"${PYTHON_BIN}" - <<'PY'
import json, os, shlex

settings_path = os.environ["SETTINGS_PATH"]
hook_path = os.environ["HOOK_PATH"]
python_bin = os.environ["PYTHON_BIN"]

data = {}
if os.path.exists(settings_path):
    with open(settings_path, encoding="utf-8") as f:
        data = json.load(f)
if not isinstance(data, dict):
    raise SystemExit(f"❌ {settings_path} は JSON object ではありません。手動で確認してください")

existing = data.get("statusLine")
if isinstance(existing, dict) and "usage-statusline" not in str(existing.get("command", "")):
    data.setdefault("usage", {})["previousStatusLine"] = existing
    print("ℹ 既存の statusLine を settings.usage.previousStatusLine に退避しました")

command = f"{shlex.quote(python_bin)} {shlex.quote(hook_path)}"
data["statusLine"] = {"type": "command", "command": command}

with open(settings_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY

echo
echo "✓ インストールが完了しました"
echo "→ Claude Code を完全に終了（Cmd+Q）してから開き直してください。"
echo "  その後、usage の画面で「今すぐ更新」を押すと数値が表示されます。"
