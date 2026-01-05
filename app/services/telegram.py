"""
Telegram Notification Service.
Sends alerts when watched products restock or match criteria.
"""

import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send notifications via Telegram Bot API."""
    
    def __init__(self, bot_token: str, chat_id: str):
        """
        Initialize the notifier.
        
        Args:
            bot_token: Telegram Bot API token (from @BotFather)
            chat_id: Target chat/user ID to send messages to
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_base = f"https://api.telegram.org/bot{bot_token}"
        self.enabled = bool(bot_token and chat_id)
        
        if not self.enabled:
            logger.warning("Telegram notifier disabled: missing bot_token or chat_id")
    
    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send a message to the configured chat.
        
        Args:
            text: Message text (supports HTML formatting)
            parse_mode: "HTML" or "Markdown"
            
        Returns:
            True if message sent successfully
        """
        if not self.enabled:
            logger.debug("Telegram disabled, skipping message")
            return False
        
        try:
            response = requests.post(
                f"{self.api_base}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode
                },
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("Telegram message sent successfully")
                return True
            else:
                logger.error(f"Telegram API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    def send_restock_alert(self, product_name: str, sku: int, 
                           old_stock: int, new_stock: int,
                           price: Optional[float] = None,
                           margin: Optional[float] = None) -> bool:
        """
        Send a formatted restock alert.
        
        Args:
            product_name: Name of the product
            sku: Product SKU
            old_stock: Previous stock level (usually 0)
            new_stock: Current stock level
            price: Optional selling price
            margin: Optional margin in MAD
        """
        emoji = "🚨" if old_stock == 0 else "📦"
        
        message = f"""
{emoji} <b>RESTOCK ALERT</b>

<b>{product_name}</b>
SKU: {sku}
Stock: {old_stock} → <b>{new_stock}</b>
"""
        
        if price:
            message += f"Price: {price:.2f} MAD\n"
        if margin:
            message += f"Margin: {margin:.2f} MAD\n"
        
        return self.send_message(message)
    
    def send_opportunity_alert(self, product_name: str, sku: int,
                               daily_profit: float, velocity: float,
                               margin: float, stock: int) -> bool:
        """
        Send a formatted opportunity alert (high-value product detected).
        """
        message = f"""
💰 <b>GOLD MINE OPPORTUNITY</b>

<b>{product_name}</b>
SKU: {sku}

📊 Daily Profit: <b>{daily_profit:.2f} MAD</b>
📦 Velocity: {velocity:.1f}/day
💵 Margin: {margin:.2f} MAD
🏷️ Stock: {stock}
"""
        return self.send_message(message)
    
    def test_connection(self) -> bool:
        """Test the Telegram bot connection."""
        if not self.enabled:
            return False
            
        try:
            response = requests.get(
                f"{self.api_base}/getMe",
                timeout=10
            )
            if response.status_code == 200:
                bot_info = response.json().get('result', {})
                logger.info(f"Telegram bot connected: @{bot_info.get('username', 'unknown')}")
                return True
            return False
        except Exception as e:
            logger.error(f"Telegram connection test failed: {e}")
            return False


def create_notifier_from_config() -> TelegramNotifier:
    """Create TelegramNotifier from config.yaml."""
    from ..core.config import get_config
    
    config = get_config()
    
    bot_token = config.get('telegram', 'bot_token', default='')
    chat_id = config.get('telegram', 'chat_id', default='')
    
    return TelegramNotifier(bot_token, str(chat_id))
