"""
データベース管理モジュール
SQLiteを使用したギルド設定と通知ログの管理
"""

import aiosqlite
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import os

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db_dir = Path(db_path).parent
        self.db_dir.mkdir(parents=True, exist_ok=True)

    async def initialize_database(self) -> None:
        """データベースとテーブルを初期化"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # guild_settingsテーブル作成
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS guild_settings (
                        guild_id INTEGER PRIMARY KEY,
                        notification_channel_id INTEGER,
                        delay_seconds INTEGER DEFAULT 60,
                        enabled BOOLEAN DEFAULT 1,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # notification_logsテーブル作成
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS notification_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER,
                        user_id INTEGER,
                        channel_id INTEGER,
                        join_time DATETIME,
                        notification_time DATETIME,
                        status TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # インデックス作成
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_notification_logs_guild_user 
                    ON notification_logs(guild_id, user_id)
                """)

                await db.commit()
                logger.info("データベース初期化完了")

        except Exception as e:
            logger.error(f"データベース初期化エラー: {e}")
            raise

    async def get_guild_settings(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """ギルド設定を取得"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM guild_settings WHERE guild_id = ?",
                    (guild_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None

        except Exception as e:
            logger.error(f"ギルド設定取得エラー (guild_id: {guild_id}): {e}")
            return None

    async def update_guild_setting(self, guild_id: int, key: str, value: Any) -> bool:
        """ギルド設定を更新"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 設定が存在するかチェック
                async with db.execute(
                    "SELECT guild_id FROM guild_settings WHERE guild_id = ?",
                    (guild_id,)
                ) as cursor:
                    exists = await cursor.fetchone()

                if exists:
                    # 既存設定を更新
                    await db.execute(f"""
                        UPDATE guild_settings 
                        SET {key} = ?, updated_at = CURRENT_TIMESTAMP 
                        WHERE guild_id = ?
                    """, (value, guild_id))
                else:
                    # 新規設定を挿入
                    await db.execute(f"""
                        INSERT INTO guild_settings (guild_id, {key}) 
                        VALUES (?, ?)
                    """, (guild_id, value))

                await db.commit()
                logger.info(f"ギルド設定更新: guild_id={guild_id}, {key}={value}")
                return True

        except Exception as e:
            logger.error(f"ギルド設定更新エラー (guild_id: {guild_id}): {e}")
            return False

    async def log_notification(self, guild_id: int, user_id: int, channel_id: int, 
                             join_time: datetime, notification_time: Optional[datetime] = None,
                             status: str = 'scheduled') -> bool:
        """通知ログを記録"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO notification_logs 
                    (guild_id, user_id, channel_id, join_time, notification_time, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (guild_id, user_id, channel_id, join_time, notification_time, status))

                await db.commit()
                logger.debug(f"通知ログ記録: guild_id={guild_id}, user_id={user_id}, status={status}")
                return True

        except Exception as e:
            logger.error(f"通知ログ記録エラー: {e}")
            return False

    async def update_notification_status(self, guild_id: int, user_id: int, 
                                       channel_id: int, status: str,
                                       notification_time: Optional[datetime] = None) -> bool:
        """通知ステータスを更新"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE notification_logs 
                    SET status = ?, notification_time = ?
                    WHERE guild_id = ? AND user_id = ? AND channel_id = ?
                    AND status = 'scheduled'
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (status, notification_time, guild_id, user_id, channel_id))

                await db.commit()
                logger.debug(f"通知ステータス更新: user_id={user_id}, status={status}")
                return True

        except Exception as e:
            logger.error(f"通知ステータス更新エラー: {e}")
            return False

    async def cleanup_old_logs(self, days: int = 30) -> bool:
        """古いログを削除"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    DELETE FROM notification_logs 
                    WHERE created_at < datetime('now', '-{} days')
                """.format(days))

                deleted_count = db.total_changes
                await db.commit()
                logger.info(f"古いログ削除完了: {deleted_count}件")
                return True

        except Exception as e:
            logger.error(f"ログクリーンアップエラー: {e}")
            return False


# シングルトンインスタンス
_db_manager = None


def get_db_manager() -> DatabaseManager:
    """DatabaseManagerのシングルトンインスタンスを取得"""
    global _db_manager
    if _db_manager is None:
        db_path = os.getenv('DATABASE_PATH', './data/bot.db')
        _db_manager = DatabaseManager(db_path)
    return _db_manager