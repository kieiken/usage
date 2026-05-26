# usage

日本語 · [English](README.en.md)

[![CI](https://github.com/kieiken/usage/actions/workflows/check.yml/badge.svg)](https://github.com/kieiken/usage/actions/workflows/check.yml)
[![Latest Release](https://img.shields.io/github/v/release/kieiken/usage)](https://github.com/kieiken/usage/releases/latest)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos/)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)

`usage` は macOS のメニューバーに **Claude Desktop / Claude Code / Codex** の使用量を表示する小さなアプリです。クリックすると、セッション使用量、週間使用量、プロジェクト別使用量、今日の token 数と概算コストを確認できます。

このリポジトリは、lollapalooza 氏によるオリジナルの [`aqua5230/usage`](https://github.com/aqua5230/usage) をもとに、Claude Code CLI だけでなく **Claude Desktop のローカルログから推算した使用量** も読めるようにした二次改造版です。帰属とライセンスについては [NOTICE.md](NOTICE.md) を参照してください。

## 特徴

- Claude Desktop のローカルログから 5 時間 / 週間の使用量を推算
- Claude Code CLI の statusLine hook にも対応
- Codex CLI の `~/.codex/sessions/` から使用量を読み取り
- macOS メニューバー常駐
- プロジェクト別 token / コスト表示
- 日本語 UI
- Anthropic / OpenAI API は呼びません
- Keychain は読みません

## 重要な考え方

このアプリは、Claude や OpenAI に問い合わせて使用量を取得するものではありません。ローカルに保存されたファイルを読みます。

Claude 側の読み取り優先順位:

1. `~/.claude/usage-status-derived.json`  
   Claude Desktop 用の推算スクリプトが毎分生成します。
2. `~/.claude/usage-status.json`  
   Claude Code の statusLine hook が生成します。
3. `~/.claude/usag-status.json`  
   古いバージョン用の互換ファイルです。
4. `~/.claude/tt-status.json`  
   token-tracker 互換のフォールバックです。

Codex 側は `~/.codex/sessions/` 以下の `*.jsonl` を読みます。Codex を使っていない場合は Codex 欄だけ非表示になります。

## いちばん簡単なインストール

GitHub Releases から `usage-installer.pkg` をダウンロードして、ダブルクリックしてください。

[最新版のインストーラをダウンロード](https://github.com/kieiken/usage/releases/latest/download/usage-installer.pkg)

インストーラは次をまとめて行います。

- `usage.app` を `/Applications` にインストール
- Claude Desktop 使用量推算スクリプトをインストール
- 毎分 `~/.claude/usage-status-derived.json` を更新する LaunchAgent を登録

未署名のため、macOS に止められた場合は `usage-installer.pkg` を右クリックして「開く」を選んでください。

## ターミナルでインストール

ターミナルで入れる場合はこちらです。

```bash
bash <(curl -fsSL https://github.com/kieiken/usage/releases/latest/download/install.sh)
```

この方法でも `/Applications/usage.app` と Claude Desktop 用 LaunchAgent が入ります。

## インストール後にすること

1. `/Applications/usage.app` を開く
2. メニューバーに `🐾` のアイコンが出る
3. アイコンをクリックする
4. 「今すぐ更新」を押す

Claude Desktop のログがある場合は、Claude Code CLI の hook を入れなくても使用量が表示されます。

## Claude Code CLI も読みたい場合

Claude Code CLI の statusLine 使用量も読みたい場合は、アプリの画面下部に出る「フックをインストール」を押してください。手動で実行する場合は次の通りです。

```bash
cd /Applications/usage.app/Contents/Resources
python3 main.py --setup
```

ソースから実行している場合:

```bash
cd /path/to/usage
python3 main.py --setup
```

実行後、Claude Code を完全に終了してから開き直してください。

削除する場合:

```bash
python3 main.py --unsetup
```

## 表示内容

メニューバーのポップオーバーには主に次が表示されます。

- Claude Code / Claude Desktop のセッション使用量
- Claude Code / Claude Desktop の週間使用量
- Codex のセッション使用量
- Codex の週間使用量
- プロジェクト別使用量
- 今日の token 数
- 今日の概算コスト
- リセットまでの時間

## パネル切替

右上の「パネル切替」から見た目を変更できます。

現在の主なパネル:

- デフォルト
- マトリックス
- Windows 95
- レトロ新聞
- 雲観測
- 真夜中の水族館
- プリズムアーケード
- ブラックホール
- ワールドカップ 2026

同じメニューから「ログイン時に起動」も切り替えられます。

## アップデート

新しいバージョンが出たら、GitHub Releases から `usage-installer.pkg` をもう一度ダウンロードして開いてください。既存の `usage.app` と LaunchAgent が更新されます。

## アンインストール

アプリ本体を削除:

```bash
rm -rf /Applications/usage.app
```

Claude Desktop 用 LaunchAgent を削除:

```bash
bash <(curl -fsSL https://github.com/kieiken/usage/releases/latest/download/uninstall-desktop-deriver.sh)
```

ローカルにある使用量 JSON も消したい場合:

```bash
rm -f ~/.claude/usage-status-derived.json
```

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| メニューバーに何も出ない | アプリが起動していない | `/Applications/usage.app` を開いてください |
| 表示が `--` のまま | 使用量 JSON がまだ生成されていない | Claude Desktop を一度開き、数分待ってから「今すぐ更新」を押してください |
| Claude Desktop の使用量が出ない | LaunchAgent が動いていない | `launchctl print gui/$(id -u)/com.lollapalooza.usage.deriver` で確認してください |
| Claude Code CLI の数値が出ない | statusLine hook が未設定 | 「フックをインストール」を押すか、`python3 main.py --setup` を実行してください |
| Codex 欄が空 | Codex のログがない | Codex で一度会話してから更新してください |
| UI が日本語にならない | 古い app が起動している可能性 | メニューバーの usage を終了し、最新版の `usage-installer.pkg` で入れ直してください |
| macOS に止められる | 未署名アプリのため | Finder で右クリックして「開く」を選んでください |

## 開発者向け

ソースから起動:

```bash
git clone https://github.com/kieiken/usage.git
cd usage
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python3 main.py
```

プレビュー:

```bash
python3 main.py --mock
python3 main.py --tui --mock
```

`.app` を作る:

```bash
./scripts/build_app.sh
```

ダブルクリック用 `.pkg` を作る:

```bash
./scripts/build_pkg.sh
```

チェック:

```bash
ruff check .
mypy .
pytest
```

## 配布ファイル

Release には次のファイルを置きます。

```text
usage-installer.pkg
usage.app.zip
install.sh
install-desktop-deriver.sh
uninstall-desktop-deriver.sh
usage-claude-desktop-deriver.py
SHA256SUMS
```

通常の利用者には `usage-installer.pkg` を案内してください。

## ライセンスと帰属

このプロジェクトは AGPL-3.0-only です。オリジナルの著作権表示は [LICENSE](LICENSE) に残しています。

この二次改造版を再配布する場合も、オリジナル作者 lollapalooza 氏と元プロジェクトへのリンクを残してください。

元プロジェクト: https://github.com/aqua5230/usage
