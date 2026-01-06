
"""
Test script to force send an Order Alert for the latest order in DB.
Useful for verifying Telegram format without waiting for new orders.
"""
import logging
from app.core.database import get_database
from app.services.telegram import create_notifier_from_config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_alert():
    # 1. Setup
    db = get_database()
    notifier = create_notifier_from_config()
    
    if not notifier.enabled:
        logger.error("Telegram not configured!")
        return

    # 2. Get latest order
    # orders table: id, number, ...
    # We use get_orders from service or db
    # db.get_orders returns list of dicts
    orders = db.get_orders(limit=1)
    
    if not orders:
        logger.error("No orders found in DB to test with.")
        return
        
    order_data = orders[0]
    logger.info(f"Testing with Order #{order_data['number']}")
    
    # 3. Reconstruct Order Object (similar to service.sync_orders output)
    # The DB record needs to be formatted for the message logic
    # The message logic expects:
    # {
    #   'number': str,
    #   'total_amount': float,
    #   'billing': {'first_name': ...},
    #   'fulfillability': 'full'|'partial'|'out_of_stock',
    #   'items': [ {'quantity':.., 'name':.., 'stock_status':.., 'available_qty':..} ]
    # }
    
    # db.get_orders returns items in 'items' key
    
    # 4. Format Message (Logic copied from Scheduler)
    # ------------------------------------------------
    o = order_data
    items = o['items'] 
    
    # Check fulfillability
    fulfillability = o['fulfillability']
    
    icon = "🟢" if fulfillability == 'full' else ("jw" if fulfillability == 'partial' else "🔴")
    # Using 'jw' was a typo in my thought? No, Orange circle maybe? 
    if fulfillability == 'partial': icon = "🟠"
    if fulfillability == 'out_of_stock': icon = "🔴"
    
    msg = f"{icon} <b>Nouvelle Commande #{o['number']}</b>\n"
    msg += f"👤 {o.get('first_name', '')} {o.get('last_name', '')}\n"
    msg += f"💰 {o['total_amount']} MAD\n"
    msg += f"📦 Status: <b>{fulfillability.upper().replace('_', ' ')}</b>\n\n"
    
    for item in items:
        # Item status icon
        i_icon = "✅"
        if item['stock_status'] == 'partial': i_icon = "⚠️"
        if item['stock_status'] == 'out_of_stock': i_icon = "❌"
        
        msg += f"{i_icon} <b>{item['quantity']}x {item['product_name'][:30]}</b>\n"
        
        # Details if issue
        if item['stock_status'] != 'instock':
            avail = item['available_qty']
            msg += f"   <i>Stock: {avail} (Manquant: {item['quantity'] - avail})</i>\n"
            
    msg += "\n<a href='https://Pharmastock.ma/client_dash/commandes'>Voir Commande</a>"
    # ------------------------------------------------
    
    # 5. Send
    logger.info("Sending message...")
    result = notifier.send_message(msg)
    
    if result:
        logger.info("✅ Alert Sent!")
    else:
        logger.error("❌ Failed to send alert.")

if __name__ == "__main__":
    test_alert()
