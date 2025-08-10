"""
VC Delay Notifier Bot
メインエントリーポイント

ボイスチャンネル参加通知を遅延送信するDiscord Bot
"""

import asyncio
import logging
import signal
import sys

import discord
from discord.ext import commands, tasks

from .config import config
from .database import get_db_manager
from .notification_manager import NotificationManager

logger = logging.getLogger(__name__)


class VCDelayBot(commands.Bot):
    """VC Delay Notifier Bot クラス"""
    
    def __init__(self):
        # 最小限のIntentsを設定
        intents = discord.Intents.default()
        intents.voice_states = True  # Voice State更新に必須
        intents.guilds = True       # ギルド情報取得に必須
        intents.message_content = False  # メッセージ内容は不要
        
        super().__init__(
            command_prefix='!vc',  # プレフィックスコマンドは使用しないが設定
            intents=intents,
            help_command=None,  # デフォルトヘルプを無効化
            case_insensitive=True
        )
        
        self.notification_manager: NotificationManager = None
        self.db = get_db_manager()
    
    async def setup_hook(self) -> None:
        """Bot初期化時のセットアップ"""
        logger.info("Botセットアップ開始...")
        
        # データベース初期化
        await self.db.initialize_database()
        
        # 通知マネージャー初期化
        self.notification_manager = NotificationManager(self)
        
        # コマンド読み込み（パッケージ絶対パス）
        await self.load_extension('vc_delay_notifier.commands')
        
        # バックグラウンドタスク開始
        self.cleanup_task.start()
        
        logger.info("Botセットアップ完了")
    
    async def on_ready(self) -> None:
        """Bot準備完了時のイベント"""
        logger.info(f'Bot準備完了: {self.user} (ID: {self.user.id})')
        logger.info(f'参加サーバー数: {len(self.guilds)}')

        # 参加サーバーの詳細をログに出力
        logger.info("参加サーバー一覧:")
        for guild in self.guilds:
            logger.info(f"  - {guild.name} (ID: {guild.id})")

        # アクティビティ設定
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="ボイスチャンネル | /help でヘルプ"
        )
        await self.change_presence(activity=activity)

        # スラッシュコマンド同期
        try:
            synced = await self.tree.sync()
            logger.info(f'スラッシュコマンド同期完了: {len(synced)}個')       
        except Exception as e:
            logger.error(f'スラッシュコマンド同期エラー: {e}')
    
    async def on_voice_state_update(self, member: discord.Member, 
                                   before: discord.VoiceState, 
                                   after: discord.VoiceState) -> None:
        """Voice State更新イベント"""
        # Botは無視
        if member.bot:
            return
        
        try:
            # 入室処理
            if before.channel is None and after.channel is not None:
                await self.notification_manager.handle_voice_join(member, after.channel)
            
            # 退室処理
            elif before.channel is not None and after.channel is None:
                await self.notification_manager.handle_voice_leave(member, before.channel)
            
            # チャンネル移動処理
            elif (before.channel is not None and after.channel is not None 
                  and before.channel != after.channel):
                await self.notification_manager.handle_voice_move(
                    member, before.channel, after.channel
                )
                
        except Exception as e:
            logger.error(f'Voice State更新処理エラー: {e}', exc_info=True)
    
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """ギルド参加時のイベント"""
        logger.info(f'新しいギルドに参加: {guild.name} (ID: {guild.id})')
        
        # 初期設定をデータベースに作成
        await self.db.update_guild_setting(guild.id, 'enabled', True)
    
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """ギルド退出時のイベント"""
        logger.info(f'ギルドから退出: {guild.name} (ID: {guild.id})')
    
    async def on_disconnect(self) -> None:
        """Discord切断時のイベント"""
        logger.warning("Discordから切断されました。再接続を試行します...")
    
    async def on_resumed(self) -> None:
        """Discord再接続時のイベント"""
        logger.info("Discord接続が再開されました")
    
    async def on_error(self, event: str, *args, **kwargs) -> None:
        """エラーハンドリング"""
        logger.error(f'イベントエラー: {event}', exc_info=True)
    
    @tasks.loop(hours=24)
    async def cleanup_task(self) -> None:
        """日次クリーンアップタスク"""
        try:
            logger.info("日次クリーンアップ実行中...")
            await self.db.cleanup_old_logs(days=config.NOTIFICATION_LOG_RETENTION_DAYS)
            logger.info("日次クリーンアップ完了")
        except Exception as e:
            logger.error(f'クリーンアップエラー: {e}')
    
    @cleanup_task.before_loop
    async def before_cleanup_task(self) -> None:
        """クリーンアップタスク開始前の待機"""
        await self.wait_until_ready()
    
    async def close(self) -> None:
        """Bot終了処理"""
        logger.info("Bot終了処理開始...")
        
        # バックグラウンドタスク停止
        self.cleanup_task.cancel()
        
        # 実行中の通知タスクをキャンセル
        if self.notification_manager:
            self.notification_manager.cancel_all_pending()
        
        await super().close()
        logger.info("Bot終了処理完了")


async def main() -> None:
    """メイン関数"""
    # 設定初期化
    config.setup_logging()
    
    # 設定検証
    if not config.validate():
        logger.error("設定エラーのため終了します")
        sys.exit(1)
    
    # Bot起動
    bot = VCDelayBot()
    
    # シグナルハンドラー設定（Ctrl+C対応）
    def signal_handler(signum, frame):
        logger.info(f"終了シグナル受信: {signum}")
        asyncio.create_task(bot.close())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        logger.info("VC Delay Notifier Bot 起動中...")
        await bot.start(config.DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        logger.error("Discord認証に失敗しました。トークンを確認してください。")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Bot実行エラー: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if not bot.is_closed():
            await bot.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("キーボード割り込みにより終了")
    except Exception as e:
        logger.error(f"予期しないエラー: {e}", exc_info=True)
        sys.exit(1)