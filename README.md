# VC Delay Notifier

ボイスチャンネル参加通知を遅延送信するDiscord Botです。間違って参加した場合の通知を回避できます。

## 機能

- ✅ ボイスチャンネル参加通知の遅延送信（5秒-10分）
- ✅ 参加後すぐ退出した場合の通知キャンセル
- ✅ チャンネル移動時の適切な処理
- ✅ スラッシュコマンドによる設定管理
- ✅ セキュアな設定とログ管理
- ✅ SQLiteデータベースによる永続化

## セットアップ

### 1. 環境準備

```bash
# 仮想環境作成
python -m venv botenv

# 仮想環境アクティベート（Windows）
botenv\Scripts\activate

# 依存関係インストール
pip install -r requirements.txt
```

### 2. 設定ファイル

`.env`ファイルを作成してDiscord Bot Tokenを設定：

```env
DISCORD_BOT_TOKEN=your_discord_bot_token_here
ENVIRONMENT=production
LOG_LEVEL=INFO
DATABASE_PATH=./data/bot.db
DEFAULT_DELAY_SECONDS=60
MAX_DELAY_SECONDS=600
MIN_DELAY_SECONDS=5
```

### 3. Bot実行

```bash
python -m vc_delay_notifier
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

### VMセットアップ（Clone方式・手動）

```bash
# 必要パッケージ
sudo apt update && sudo apt -y install git python3 python3-venv python3-pip

# コード取得
git clone https://github.com/technical-art-server/vc-delay-notifier.git
cd vc-delay-notifier

# 仮想環境
python3 -m venv ~/discord_bot_env
source ~/discord_bot_env/bin/activate
python -m pip install -U pip
pip install -r requirements.txt

# 環境変数（いずれかの方法で設定）
# 1) .env を作成
cp .env.example .env && nano .env   # DISCORD_BOT_TOKEN 等を設定
# 2) もしくはシェルで一時的に
# export DISCORD_BOT_TOKEN=YOUR_TOKEN

# 起動確認
python -m vc_delay_notifier
```

### Google Compute Engine（無料枠）

```bash
# systemdサービス設定
sudo nano /etc/systemd/system/vcdelay.service

# サービス開始
sudo systemctl daemon-reload
sudo systemctl enable vcdelay
sudo systemctl start vcdelay
```

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

