"""
Telegram Bot Service для відправки повідомлень в канал
"""
import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramService:
    def __init__(self, bot_token: str, channel_id: str):
        """
        Ініціалізація Telegram сервісу
        
        Args:
            bot_token: Токен бота від @BotFather
            channel_id: ID каналу (наприклад: @ProSvitlo_Khm або -100123456789)
        """
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_message(
        self,
        message: str,
        parse_mode: str = "HTML",
        disable_notification: bool = False
    ) -> bool:
        """
        Відправити повідомлення в Telegram канал
        
        Args:
            message: Текст повідомлення (підтримує HTML або Markdown)
            parse_mode: Режим форматування ("HTML" або "Markdown")
            disable_notification: Відправити без звуку
        
        Returns:
            bool: True якщо успішно відправлено
        """
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                "chat_id": self.channel_id,
                "text": message,
                "parse_mode": parse_mode,
                "disable_notification": disable_notification,
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            logger.info(f"✅ Telegram message sent to {self.channel_id}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to send Telegram message: {e}")
            return False
    
    def send_announcement(self, title: str, body: str, source: str = "") -> bool:
        """
        Відправити оголошення з форматуванням
        
        Args:
            title: Заголовок оголошення
            body: Текст оголошення
            source: Джерело (опціонально)
        
        Returns:
            bool: True якщо успішно
        """
        # Форматуємо повідомлення з HTML
        message = f"<b>📢 {title}</b>\n\n{body}"
        
        if source:
            message += f"\n\n<i>Джерело: {source}</i>"
        
        return self.send_message(message)
    
    def send_outage_warning(
        self,
        queue: str,
        time: str,
        date: Optional[str] = None
    ) -> bool:
        """
        Відправити попередження про відключення
        
        Args:
            queue: Номер черги
            time: Час відключення
            date: Дата (опціонально)
        
        Returns:
            bool: True якщо успішно
        """
        date_text = f" на {date}" if date else ""
        message = (
            f"<b>⚡ Відключення черги {queue}</b>\n\n"
            f"⏰ О {time}{date_text} буде відключено електроенергію\n\n"
            f"Черга: <code>{queue}</code>"
        )
        
        return self.send_message(message)


# Singleton instance (буде ініціалізовано в main.py)
_telegram_service: Optional[TelegramService] = None


def init_telegram_service(bot_token: str, channel_id: str) -> TelegramService:
    """Ініціалізувати глобальний Telegram сервіс"""
    global _telegram_service
    _telegram_service = TelegramService(bot_token, channel_id)
    return _telegram_service


def get_telegram_service() -> Optional[TelegramService]:
    """Отримати ініціалізований Telegram сервіс"""
    return _telegram_service
