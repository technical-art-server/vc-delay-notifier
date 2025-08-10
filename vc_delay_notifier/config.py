"""
設定管理モジュール
環境変数とデフォルト値の管理
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    """Bot設定クラス"""
    
    # Discord設定
    DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    
    # 環境設定
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # データベース設定
    DATABASE_PATH = os.getenv('DATABASE_PATH', './data/bot.db')
    
    # Bot設定
    DEFAULT_DELAY_SECONDS = int(os.getenv('DEFAULT_DELAY_SECONDS', '60'))
    MAX_DELAY_SECONDS = int(os.getenv('MAX_DELAY_SECONDS', '600'))
    MIN_DELAY_SECONDS = int(os.getenv('MIN_DELAY_SECONDS', '5'))
    # 通知ログの保持日数（DBクリーンアップ用）
    NOTIFICATION_LOG_RETENTION_DAYS = int(os.getenv('NOTIFICATION_LOG_RETENTION_DAYS', '30'))
    
    # ログ設定
    LOG_DIR = Path('./logs')
    LOG_FILE = LOG_DIR / 'bot.log'
    
    @classmethod
    def validate(cls) -> bool:
        """設定値の妥当性をチェック"""
        if not cls.DISCORD_BOT_TOKEN:
            logger.error("DISCORD_BOT_TOKENが設定されていません")
            return False
            
        if cls.MIN_DELAY_SECONDS > cls.MAX_DELAY_SECONDS:
            logger.error("MIN_DELAY_SECONDSがMAX_DELAY_SECONDSより大きいです")
            return False
            
        if not (cls.MIN_DELAY_SECONDS <= cls.DEFAULT_DELAY_SECONDS <= cls.MAX_DELAY_SECONDS):
            logger.error("DEFAULT_DELAY_SECONDSが範囲外です")
            return False

        if cls.NOTIFICATION_LOG_RETENTION_DAYS < 1:
            logger.error("NOTIFICATION_LOG_RETENTION_DAYS は1以上である必要があります")
            return False
            
        return True
    
    @classmethod
    def setup_logging(cls) -> None:
        """ロギング設定を初期化"""
        # ログディレクトリ作成
        cls.LOG_DIR.mkdir(exist_ok=True)
        
        # ログレベル設定
        log_level = getattr(logging, cls.LOG_LEVEL.upper(), logging.INFO)
        
        # ロガー設定
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(cls.LOG_FILE, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        
        # Discordライブラリのログレベルを調整
        discord_logger = logging.getLogger('discord')
        discord_logger.setLevel(logging.WARNING)
        
        logger.info(f"ロギング設定完了 - レベル: {cls.LOG_LEVEL}, ファイル: {cls.LOG_FILE}")


# グローバル設定インスタンス
config = Config()