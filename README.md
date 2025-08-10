# VC Delay Notifier

ボイスチャンネル参加通知を遅延送信するDiscord Botです。間違って参加した場合の通知を回避できます。

## 機能

- ✅ ボイスチャンネル参加通知の遅延送信（5秒-10分）
- ✅ 参加後すぐ退出した場合の通知キャンセル
- ✅ チャンネル移動時の適切な処理
- ✅ スラッシュコマンドによる設定管理
- ✅ セキュアな設定とログ管理
- ✅ SQLiteデータベースによる永続化

## セットアップ/デプロイメント

1) リポジトリ取得と環境準備（Debian/Ubuntu 例）

```bash
sudo apt update && sudo apt -y install git python3 python3-venv python3-pip
git clone https://github.com/technical-art-server/vc-delay-notifier.git
cd vc-delay-notifier

python3 -m venv ~/discord_bot_env
source ~/discord_bot_env/bin/activate
python -m pip install -U pip
pip install -r requirements.txt
```

2) 設定（.env または環境変数）

```env
DISCORD_BOT_TOKEN=your_discord_bot_token_here
ENVIRONMENT=production
LOG_LEVEL=INFO
DATABASE_PATH=./data/bot.db
DEFAULT_DELAY_SECONDS=60
MAX_DELAY_SECONDS=600
MIN_DELAY_SECONDS=5
```

3) 起動確認（前景実行）

```bash
python -m vc_delay_notifier
```

4) 常駐化（systemd）

```bash
sudo tee /etc/systemd/system/vcdelay.service >/dev/null <<'UNIT'
[Unit]
Description=VC Delay Notifier Bot
After=network.target

[Service]
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/vc-delay-notifier
Environment="DISCORD_BOT_TOKEN=${DISCORD_BOT_TOKEN}"
Environment="LOG_LEVEL=INFO"
Environment="DATABASE_PATH=/home/YOUR_USER/vc-delay-notifier/data/bot.db"
ExecStart=/home/YOUR_USER/discord_bot_env/bin/python -m vc_delay_notifier
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable vcdelay
sudo systemctl start vcdelay
```

## コマンド一覧

| コマンド | 説明 | 権限 |
|---------|-----|------|
| `/setchannel` | 通知送信先チャンネルを設定 | チャンネル管理 |
| `/setdelay` | 通知遅延時間を設定（5-600秒） | チャンネル管理 |
| `/enable` | 通知を有効化 | チャンネル管理 |
| `/disable` | 通知を無効化 | チャンネル管理 |
| `/status` | 現在の設定状況を確認 | チャンネル管理 |
| `/help` | ヘルプを表示 | 全員 |

## 使い方

1. Botをサーバーに招待
2. `/setchannel`で通知チャンネルを設定
3. `/setdelay`で遅延時間を調整（任意）
4. `/enable`で通知を有効化
5. ボイスチャンネルに参加して動作確認

## 入退室通知フロー

- 入室
  - 0→1人（非Bot）のときのみ遅延入室タスクをスケジュール
  - 遅延時間経過時点でまだ同じVCにいる場合に入室通知を送信
  - 2人以上すでに在室の場合は入室通知を送らない

- 退出
  - 1→0人（非Bot）になったときのみ退出通知を送信
  - 在室者が残っている場合は退出通知を送らない

- 移動
  - 移動元では退出フローを適用（1→0なら退出通知）
  - 移動先では入室フローを適用（0→1なら遅延入室タスク）

- データベース更新
  - 入室時: scheduled を記録（0→1のみ）
  - 入室通知送信: sent に更新
  - 遅延中に退出/移動で中断: cancelled に更新

## ディレクトリ構造

```
vc-delay-notifier/
├── requirements.txt           # 依存関係
├── README.md
├── .env                       # 環境変数（任意。VMではsystemdのEnvironment等でも可）
├── .gitignore
├── data/                      # データベースファイル（実行時に自動作成）
├── logs/                      # ログファイル（実行時に自動作成）
└── vc_delay_notifier/         # Pythonパッケージ
    ├── __init__.py
    ├── __main__.py            # エントリポイント（python -m vc_delay_notifier）
    ├── config.py              # 設定管理
    ├── database.py            # データベース管理
    ├── commands.py            # スラッシュコマンド
    └── notification_manager.py# 通知管理
```

## 必要なDiscord権限

- `Send Messages` - メッセージ送信
- `Embed Links` - Embed投稿
- `Use Slash Commands` - スラッシュコマンド使用
- `Connect` - ボイスチャンネル状態監視
- `View Channel` - チャンネル情報取得

## セキュリティ

- 🔒 環境変数による機密情報管理
- 🔒 最小権限Intents設定
- 🔒 入力値検証とサニタイゼーション
- 🔒 ログローテーション
- 🔒 エラー情報の適切な隠蔽

## デプロイメント

## 開発者向け

### ログ確認

```bash
# リアルタイムログ
tail -f logs/bot.log

# サービス状態確認
systemctl status vcdelay
```

### データベース確認

```sql
-- 設定確認
SELECT * FROM guild_settings;

-- 通知ログ確認
SELECT * FROM notification_logs ORDER BY created_at DESC LIMIT 10;
```

## トラブルシューティング

### よくある問題

1. **Bot Tokenエラー**
   - `.env`ファイルのトークン設定を確認

2. **通知が送信されない**
   - `/status`でチャンネル設定を確認
   - Bot権限を確認

3. **コマンドが表示されない**
   - Bot再起動後、数分待つ
   - `チャンネル管理`権限を確認

