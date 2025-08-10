"""
スラッシュコマンド実装モジュール
Bot設定用のコマンド群
"""

import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from .database import get_db_manager
from .config import config

logger = logging.getLogger(__name__)


class VCDelayCommands(commands.Cog):
    """VCDelayNotifierのコマンドクラス"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = get_db_manager()
    
    @app_commands.command(name="setdelay", description="通知遅延時間を設定します")
    @app_commands.describe(seconds="遅延時間（秒）- 5秒～600秒の範囲で設定")
    @app_commands.default_permissions(manage_channels=True)
    async def setdelay(self, interaction: discord.Interaction, seconds: int) -> None:
        """遅延時間設定コマンド"""
        # 入力値検証
        if not (config.MIN_DELAY_SECONDS <= seconds <= config.MAX_DELAY_SECONDS):
            await interaction.response.send_message(
                f"⚠️ 遅延時間は{config.MIN_DELAY_SECONDS}秒～{config.MAX_DELAY_SECONDS}秒（5秒～10分）の範囲で設定してください。",
                ephemeral=True
            )
            return
        
        # データベース更新
        success = await self.db.update_guild_setting(
            interaction.guild.id, 'delay_seconds', seconds
        )
        
        if success:
            await interaction.response.send_message(
                f"✅ 通知遅延時間を**{seconds}秒**（{seconds//60}分{seconds%60}秒）に設定しました。",
                ephemeral=True
            )
            logger.info(f"遅延時間設定: {interaction.guild.name} -> {seconds}秒")
        else:
            await interaction.response.send_message(
                "❌ 設定の更新に失敗しました。しばらく時間をおいて再度お試しください。",
                ephemeral=True
            )
    
    @app_commands.command(name="setchannel", description="通知送信先チャンネルを設定します")
    @app_commands.describe(channel="通知を送信するテキストチャンネル")
    @app_commands.default_permissions(manage_channels=True)
    async def setchannel(self, interaction: discord.Interaction, 
                        channel: discord.TextChannel) -> None:
        """通知チャンネル設定コマンド"""
        # チャンネル権限チェック
        permissions = channel.permissions_for(interaction.guild.me)
        if not permissions.send_messages or not permissions.embed_links:
            await interaction.response.send_message(
                f"❌ {channel.mention} に対してメッセージ送信またはEmbed投稿権限がありません。\n"
                "Botに必要な権限を付与してから再度お試しください。",
                ephemeral=True
            )
            return
        
        # データベース更新
        success = await self.db.update_guild_setting(
            interaction.guild.id, 'notification_channel_id', channel.id
        )
        
        if success:
            await interaction.response.send_message(
                f"✅ 通知チャンネルを{channel.mention}に設定しました。",
                ephemeral=True
            )
            logger.info(f"通知チャンネル設定: {interaction.guild.name} -> #{channel.name}")
        else:
            await interaction.response.send_message(
                "❌ 設定の更新に失敗しました。しばらく時間をおいて再度お試しください。",
                ephemeral=True
            )
    
    @app_commands.command(name="enable", description="ボイスチャンネル通知を有効にします")
    @app_commands.default_permissions(manage_channels=True)
    async def enable(self, interaction: discord.Interaction) -> None:
        """通知有効化コマンド"""
        success = await self.db.update_guild_setting(
            interaction.guild.id, 'enabled', True
        )
        
        if success:
            await interaction.response.send_message(
                "✅ ボイスチャンネル通知を**有効**にしました。",
                ephemeral=True
            )
            logger.info(f"通知有効化: {interaction.guild.name}")
        else:
            await interaction.response.send_message(
                "❌ 設定の更新に失敗しました。",
                ephemeral=True
            )
    
    @app_commands.command(name="disable", description="ボイスチャンネル通知を無効にします")
    @app_commands.default_permissions(manage_channels=True)
    async def disable(self, interaction: discord.Interaction) -> None:
        """通知無効化コマンド"""
        success = await self.db.update_guild_setting(
            interaction.guild.id, 'enabled', False
        )
        
        if success:
            await interaction.response.send_message(
                "🔇 ボイスチャンネル通知を**無効**にしました。",
                ephemeral=True
            )
            logger.info(f"通知無効化: {interaction.guild.name}")
        else:
            await interaction.response.send_message(
                "❌ 設定の更新に失敗しました。",
                ephemeral=True
            )
    
    @app_commands.command(name="status", description="現在の設定状況を確認します")
    @app_commands.default_permissions(manage_channels=True)
    async def status(self, interaction: discord.Interaction) -> None:
        """設定状況確認コマンド"""
        settings = await self.db.get_guild_settings(interaction.guild.id)
        
        # 設定情報作成
        embed = discord.Embed(
            title="🔧 VC Delay Notifier 設定状況",
            color=discord.Color.blue()
        )
        
        if settings:
            # 通知状態
            status_emoji = "✅" if settings['enabled'] else "🔇"
            embed.add_field(
                name="通知状態",
                value=f"{status_emoji} {'有効' if settings['enabled'] else '無効'}",
                inline=True
            )
            
            # 遅延時間
            delay = settings['delay_seconds']
            embed.add_field(
                name="遅延時間",
                value=f"{delay}秒（{delay//60}分{delay%60}秒）",
                inline=True
            )
            
            # 通知チャンネル
            if settings['notification_channel_id']:
                channel = self.bot.get_channel(settings['notification_channel_id'])
                channel_text = channel.mention if channel else "チャンネルが見つかりません"
            else:
                channel_text = "未設定"
            
            embed.add_field(
                name="通知チャンネル",
                value=channel_text,
                inline=True
            )
            
            # 最終更新
            embed.add_field(
                name="最終更新",
                value=settings['updated_at'][:16].replace('T', ' '),
                inline=False
            )
        else:
            embed.add_field(
                name="設定状況",
                value="初期設定が必要です。\n`/setchannel` で通知チャンネルを設定してください。",
                inline=False
            )
        
        embed.set_footer(text="設定を変更するには対応するコマンドを実行してください。")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="help", description="VC Delay Notifierの使い方を表示します")
    async def help_command(self, interaction: discord.Interaction) -> None:
        """ヘルプコマンド"""
        embed = discord.Embed(
            title="📚 VC Delay Notifier ヘルプ",
            description="ボイスチャンネル参加通知を遅延送信するBotです。",
            color=discord.Color.green()
        )
        
        # コマンド一覧
        commands_text = """
        `/setchannel` - 通知送信先チャンネルを設定
        `/setdelay` - 通知遅延時間を設定（5-600秒）
        `/enable` - 通知を有効化
        `/disable` - 通知を無効化
        `/status` - 現在の設定状況を確認
        `/help` - このヘルプを表示
        """
        
        embed.add_field(
            name="🔧 利用可能コマンド",
            value=commands_text.strip(),
            inline=False
        )
        
        embed.add_field(
            name="💡 使い方",
            value="1. `/setchannel` で通知チャンネルを設定\n"
                  "2. `/setdelay` で遅延時間を調整（お好みで）\n"
                  "3. `/enable` で通知を有効化\n"
                  "4. ボイスチャンネルに参加して動作確認",
            inline=False
        )
        
        embed.add_field(
            name="⚠️ 権限について",
            value="これらのコマンドは「チャンネル管理」権限を持つユーザーのみ実行できます。",
            inline=False
        )
        
        embed.set_footer(text="VC Delay Notifier | 間違って参加した場合の通知を回避")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Cogセットアップ関数"""
    await bot.add_cog(VCDelayCommands(bot))