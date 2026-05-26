# usage

日本語 · [English](README.en.md)

[![CI](https://github.com/aqua5230/usage/actions/workflows/check.yml/badge.svg)](https://github.com/aqua5230/usage/actions/workflows/check.yml)
[![Latest Release](https://img.shields.io/github/v/release/aqua5230/usage)](https://github.com/aqua5230/usage/releases/latest)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos/)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)

`usage` は macOS のメニューバーに **Claude Desktop / Claude Code / Codex** の使用量を表示するツールです。アイコンを開くと、セッション使用量、週間使用量、プロジェクト別の使用量、今日の token 数と概算コストを確認できます。

Anthropic / OpenAI の API は呼びません。Keychain も読みません。表示に使う数値は、ローカルに保存されている Claude / Codex のログや status JSON から取得します。

この配布版は、lollapalooza 氏によるオリジナルの `usage` をもとに、Claude Code CLI だけでなく Claude Desktop のローカルログから使用量を推算できるようにした二次改造版です。詳細は [NOTICE.md](NOTICE.md) を参照してください。

<p align="center">
  <img src="docs/popover.png" alt="usage のポップオーバー" width="320">
</p>

## データの取得元

Claude 側の読み取り優先順位は次の通りです。

1. `~/.claude/usage-status-derived.json`  
   Release installer が入れる Claude Desktop 使用量推算 LaunchAgent が毎分生成します。
2. `~/.claude/usage-status.json`  
   Claude Code の statusLine hook が生成します。
3. `~/.claude/usag-status.json`  
   v0.1.x 互換用の古いファイル名です。
4. `~/.claude/tt-status.json`  
   token-tracker 互換のフォールバックです。

Codex 側は `~/.codex/sessions/` 以下の `*.jsonl` を読み、`rate_limits` と token 使用量を集計します。Codex が未インストール、またはログがない場合は Codex 欄だけが非表示になります。

Codex のコスト推定に必要な価格表がローカルにない場合だけ、公開されている LiteLLM の価格表を一度取得して `~/.claude/pricing_cache.json` に 7 日間キャッシュします。失敗した場合は内蔵のフォールバック価格を使います。

## 必要なもの

- macOS
- Python 3.13
- Claude Desktop または Claude Code にログイン済みであること
- Codex は任意です

## インストール

GitHub Releases から `usage.app.zip` をダウンロードして展開し、`usage.app` を `/Applications` などへ移動してください。

ダブルクリックで入れる場合は、GitHub Releases から `usage-installer.pkg` をダウンロードして開いてください。`usage.app` と Claude Desktop 使用量推算 LaunchAgent がまとめてインストールされます。

一行でインストールする場合:

```bash
bash <(curl -fsSL https://github.com/aqua5230/usage/releases/latest/download/install.sh)
```

この installer は次の処理を行います。

- `usage.app` を `/Applications` に配置する
- Claude Desktop 使用量推算 LaunchAgent をインストールする
- `~/.claude/usage-status-derived.json` を毎分更新する
- `usage.app` を起動する

Apple Developer 証明書で署名していないため、初回起動時は Gatekeeper に止められる場合があります。その場合は Finder で `usage.app` を右クリックし、「開く」を選んで確認してください。以後は通常通り開けます。

## Claude Code hook

Claude Code CLI の使用量もそのまま読みたい場合は、初回起動時にポップオーバー下部の「フックをインストール」ボタンを押してください。手動で行う場合は次を実行します。

```bash
python3 main.py --setup
```

実行後、Claude Code を一度完全に終了してから開き直してください。

削除する場合:

```bash
python3 main.py --unsetup
```

## 開発者向け

```bash
git clone https://github.com/aqua5230/usage.git
cd usage
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python3 main.py
```

プレビューだけ見たい場合:

```bash
python3 main.py --mock
python3 main.py --tui --mock
```

配布用の `.app` を作る場合:

```bash
./scripts/build_app.sh
```

ダブルクリック用の installer `.pkg` を作る場合:

```bash
./scripts/build_pkg.sh
```

GitHub Release は `v*` tag を push すると `.github/workflows/release.yml` が `usage.app.zip` と installer 用 asset を生成して Release に添付します。

## 起動時に自動起動

アプリのポップオーバーから「パネル切替」を開き、「ログイン時に起動」をオンにしてください。

ソースから使う場合は LaunchAgent を手動で入れることもできます。

```bash
./scripts/install-launchagent.sh
launchctl start com.lollapalooza.usage
```

削除:

```bash
./scripts/uninstall-launchagent.sh
```

## オプション

- `--setup` / `--unsetup`: Claude Code statusLine hook のインストール / 削除
- `--tui`: ターミナル TUI モード
- `--interval N`: 状態ファイルの再読み込み間隔。最小 30 秒、既定値 60 秒
- `--mock`: ダミーデータで起動
- `--force-group {0,1,2,3}`: TUI 用のレート分類を強制

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| メニューバーが `--` のまま | status JSON がまだ生成されていない | installer を実行済みか確認し、Claude Desktop / Claude Code を一度開いてから「今すぐ更新」を押してください |
| Claude Code の数値が出ない | hook が未インストール、または Claude Code が statusLine をまだ更新していない | `python3 main.py --setup` を実行し、Claude Code を再起動してください |
| Codex 欄が空 | `~/.codex/sessions/` に rate limit 情報がない | Codex で一度会話し、ログが生成されるのを待ってください |
| 今日のコストが `$0.00` | モデル名が価格表と一致しない、または価格表の取得に失敗した | `~/.claude/pricing_cache.json` を削除して再取得するか、`USAGE_DEBUG=1` で起動してください |
| app が開けない | macOS Gatekeeper が未署名 app を止めている | Finder で `usage.app` を右クリックし、「開く」を選んでください |

## ライセンスと帰属

このプロジェクトは AGPL-3.0-only です。オリジナルの著作権表示は [LICENSE](LICENSE) に残しています。

この二次改造版を再配布する場合も、オリジナル作者 lollapalooza 氏と元プロジェクトへのリンクを残してください。

元プロジェクト: https://github.com/aqua5230/usage
