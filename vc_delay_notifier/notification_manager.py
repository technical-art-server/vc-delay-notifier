"""
通知管理モジュール
Voice State変更の監視と遅延通知の管理（入室・退出通知対応）
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import discord
from discord.ext import commands

from .database import get_db_manager

logger = logging.getLogger(__name__)


class NotificationManager:
    """通知管理クラス（入室・退出通知対応）"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = get_db_manager()
        # チャンネルごとの遅延入室通知タスク
        self.pending_channel_join_tasks: Dict[int, asyncio.Task] = {}
        # チャンネルセッション情報（0→1の入室で生成、1→0の退出でクローズ）
        # key: channel_id, value: {
        #   'guild_id': int,
        #   'first_member_id': int,
        #   'join_time': datetime,
        #   'join_notif_sent': bool
        # }
        self.channel_sessions: Dict[int, Dict[str, object]] = {}

    def cancel_all_pending(self) -> None:
        """全チャンネルの保留中の入室通知タスクをキャンセル"""
        for channel_id, task in list(self.pending_channel_join_tasks.items()):
            if not task.done():
                task.cancel()
            self.pending_channel_join_tasks.pop(channel_id, None)

    def _get_task_key(self, user_id: int, channel_id: int, task_type: str = "join") -> str:
        """タスクキーを生成"""
        return f"{user_id}_{channel_id}_{task_type}"

    async def handle_voice_join(self, member: discord.Member,
                               channel: discord.VoiceChannel) -> None:
        """ボイスチャンネル参加処理"""
        if member.bot:
            return

        guild_id = member.guild.id
        user_id = member.id
        channel_id = channel.id
        join_time = datetime.now()

        logger.info(f"Voice参加検知: user_id={user_id} -> {channel.name}")

        # ギルド設定取得
        settings = await self.db.get_guild_settings(guild_id)
        if not settings or not settings['enabled']:
            logger.debug(f"通知無効 - ギルド: {member.guild.name}")
            return

        if not settings['notification_channel_id']:
            logger.warning(f"通知チャンネル未設定 - ギルド: {member.guild.name}")
            return

        # 参加後のチャンネル在室人数（Bot除く）
        non_bot_members = [m for m in channel.members if not m.bot]
        if len(non_bot_members) == 1:
            # 0→1 の遷移のみ入室通知対象
            # 既存のチャンネル入室タスクがあればキャンセル
            await self._cancel_channel_join_task(channel_id)

            # セッション生成・DBにスケジュール記録
            self.channel_sessions[channel_id] = {
                'guild_id': guild_id,
                'first_member_id': user_id,
                'join_time': join_time,
                'join_notif_sent': False,
            }
            await self.db.log_notification(guild_id, user_id, channel_id, join_time, status='scheduled')

            # 遅延入室通知タスク開始
            delay_seconds = settings['delay_seconds']
            task = asyncio.create_task(
                self._delayed_join_notification(
                    member, channel, settings['notification_channel_id'],
                    delay_seconds, join_time
                )
            )
            self.pending_channel_join_tasks[channel_id] = task
            logger.info(f"遅延入室通知タスク開始: {delay_seconds}秒後 - user_id={user_id}")
        else:
            logger.debug(f"入室通知スキップ（既に在室者あり）: channel_id={channel_id}, count={len(non_bot_members)}")

    async def handle_voice_leave(self, member: discord.Member,
                                channel: discord.VoiceChannel) -> None:
        """ボイスチャンネル退出処理"""
        if member.bot:
            return

        guild_id = member.guild.id
        user_id = member.id
        channel_id = channel.id
        leave_time = datetime.now()

        logger.info(f"Voice退出検知: user_id={user_id} <- {channel.name}")

        # 退出後の在室人数（Bot除く）
        non_bot_members = [m for m in channel.members if not m.bot]

        if len(non_bot_members) == 0:
            # 1→0 の遷移
            # 未送信の入室タスクがあればキャンセル＋DB更新
            await self._cancel_channel_join_task(channel_id, update_db=True)

            session = self.channel_sessions.pop(channel_id, None)
            if session and session.get('join_notif_sent'):
                settings = await self.db.get_guild_settings(guild_id)
                if settings and settings['enabled'] and settings['notification_channel_id']:
                    await self._send_leave_notification(
                        member, channel, settings['notification_channel_id'],
                        session['join_time'], leave_time
                    )
        else:
            logger.debug(f"退出通知スキップ（まだ在室者あり）: channel_id={channel_id}, count={len(non_bot_members)}")

    async def handle_voice_move(self, member: discord.Member,
                               before_channel: discord.VoiceChannel,
                               after_channel: discord.VoiceChannel) -> None:
        """ボイスチャンネル移動処理"""
        if member.bot:
            return

        logger.info(f"Voice移動検知: user_id={member.id} {before_channel.name} -> {after_channel.name}")

        # 移動元チャンネルの処理（退出扱い）
        await self.handle_voice_leave(member, before_channel)

        # 移動先チャンネルの処理（入室扱い）
        await self.handle_voice_join(member, after_channel)

    async def _cancel_channel_join_task(self, channel_id: int, update_db: bool = False) -> None:
        """チャンネル単位の入室通知タスクをキャンセル"""
        if channel_id in self.pending_channel_join_tasks:
            task = self.pending_channel_join_tasks[channel_id]
            if not task.done():
                task.cancel()
                logger.debug(f"入室通知タスクキャンセル: channel_id={channel_id}")
            del self.pending_channel_join_tasks[channel_id]

            if update_db:
                session = self.channel_sessions.get(channel_id)
                if session:
                    await self.db.update_notification_status(
                        session['guild_id'], session['first_member_id'], channel_id, 'cancelled'
                    )

    async def _delayed_join_notification(self, member: discord.Member,
                                        voice_channel: discord.VoiceChannel,
                                        notification_channel_id: int,
                                        delay_seconds: int,
                                        join_time: datetime) -> None:
        """遅延入室通知実行"""
        try:
            # 遅延待機
            await asyncio.sleep(delay_seconds)

            # メンバーがまだチャンネルにいるかチェック
            if not member.voice or member.voice.channel.id != voice_channel.id:
                logger.debug(f"入室通知キャンセル - メンバーがチャンネルを退出: user_id={member.id}")
                return

            # 通知チャンネル取得
            notification_channel = self.bot.get_channel(notification_channel_id)
            if not notification_channel:
                logger.error(f"通知チャンネルが見つかりません: {notification_channel_id}")
                return

            # 入室通知メッセージ作成
            embed = discord.Embed(
                title="🎤 ボイスチャンネル参加通知",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            embed.add_field(name="参加者", value=member.mention, inline=True)
            embed.add_field(name="チャンネル", value=voice_channel.mention, inline=True)
            embed.add_field(name="参加時刻", value=f"<t:{int(join_time.timestamp())}:R>", inline=True)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"遅延時間: {delay_seconds}秒")

            # 通知送信（チャンネルの最初の参加のみ）
            await notification_channel.send(embed=embed)

            # 入室通知送信済みマーク（DB更新）
            session = self.channel_sessions.get(voice_channel.id)
            if session:
                session['join_notif_sent'] = True
                notification_time = datetime.now()
                await self.db.update_notification_status(
                    session['guild_id'], session['first_member_id'], voice_channel.id, 'sent', notification_time
                )

            logger.info(f"遅延入室通知送信完了: user_id={member.id} in {voice_channel.name}")

        except asyncio.CancelledError:
            logger.debug(f"遅延入室通知タスクがキャンセルされました: user_id={member.id}")
            await self.db.update_notification_status(
                member.guild.id, member.id, voice_channel.id, 'cancelled'
            )

        except Exception as e:
            logger.error(f"遅延入室通知送信エラー: {e}")
            await self.db.update_notification_status(
                member.guild.id, member.id, voice_channel.id, 'failed'
            )

        finally:
            # タスクを辞書から削除
            self.pending_channel_join_tasks.pop(voice_channel.id, None)

    async def _send_leave_notification(self, member: discord.Member,
                                      voice_channel: discord.VoiceChannel,
                                      notification_channel_id: int,
                                      join_time: datetime,
                                      leave_time: datetime) -> None:
        """退出通知送信"""
        try:
            # 通知チャンネル取得
            notification_channel = self.bot.get_channel(notification_channel_id)
            if not notification_channel:
                logger.error(f"通知チャンネルが見つかりません: {notification_channel_id}")
                return

            # 滞在時間を計算
            duration = leave_time - join_time
            duration_minutes = int(duration.total_seconds() // 60)
            duration_seconds = int(duration.total_seconds() % 60)

            # 退出通知メッセージ作成
            embed = discord.Embed(
                title="🚪 ボイスチャンネル退出通知",
                color=discord.Color.red(),
                timestamp=leave_time
            )
            embed.add_field(name="退出者", value=member.mention, inline=True)
            embed.add_field(name="チャンネル", value=voice_channel.mention, inline=True)
            embed.add_field(name="滞在時間", value=f"{duration_minutes}分{duration_seconds}秒", inline=True)
            embed.add_field(name="退出時刻", value=f"<t:{int(leave_time.timestamp())}:R>", inline=True)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text="入室通知が送信されたセッションのみ通知")

            # 通知送信
            await notification_channel.send(embed=embed)

            logger.info(f"退出通知送信完了: user_id={member.id} from {voice_channel.name}")

        except Exception as e:
            logger.error(f"退出通知送信エラー: {e}")