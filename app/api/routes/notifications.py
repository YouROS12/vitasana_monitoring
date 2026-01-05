"""
Notifications API Routes.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/test")
async def test_telegram():
    """Test Telegram notification connectivity."""
    try:
        from app.services.telegram import create_notifier_from_config
        
        notifier = create_notifier_from_config()
        
        if not notifier.enabled:
            return {
                "success": False,
                "error": "Telegram not configured. Add bot_token and chat_id to config.yaml"
            }
        
        # Test connection first
        if not notifier.test_connection():
            return {
                "success": False,
                "error": "Failed to connect to Telegram API. Check bot_token."
            }
        
        # Send test message
        result = notifier.send_message(
            "✅ <b>Vitasana Alert System</b>\n\n"
            "Test notification successful!\n"
            "Your alerts are configured correctly."
        )
        
        return {
            "success": result,
            "message": "Test notification sent!" if result else "Failed to send message"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_notification_status():
    """Get current notification configuration status."""
    try:
        from app.services.telegram import create_notifier_from_config
        
        notifier = create_notifier_from_config()
        
        return {
            "telegram_enabled": notifier.enabled,
            "has_bot_token": bool(notifier.bot_token),
            "has_chat_id": bool(notifier.chat_id)
        }
        
    except Exception as e:
        return {
            "telegram_enabled": False,
            "error": str(e)
        }
