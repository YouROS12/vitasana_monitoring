import sqlite3
conn = sqlite3.connect('vitasana.db')
c = conn.cursor()

# Find the EUCERIN ECRAN product SKU
c.execute("SELECT sku, name FROM products WHERE name LIKE '%EUCERIN ECRAN ANTI-PIGMENT%'")
product = c.fetchone()
if product:
    sku, name = product
    print(f'Product: {name}')
    print(f'SKU: {sku}')
    
    # Get latest price data from history
    c.execute('SELECT price, final_price, discount_percent FROM monitoring_history WHERE product_sku = ? ORDER BY timestamp DESC LIMIT 1', (sku,))
    price_data = c.fetchone()
    if price_data:
        price, final, disc = price_data
        margin = (price or 0) - (final or 0)
        print(f'Price: {price}, Final: {final}, Discount: {disc}%')
        print(f'Margin: {margin} MAD')
    else:
        price, final, margin = 0, 0, 0
        print('No price data!')
    
    # Check history count
    c.execute('SELECT COUNT(*) FROM monitoring_history WHERE product_sku = ?', (sku,))
    count = c.fetchone()[0]
    print(f'\nHistory records: {count}')
    
    # Check stock changes
    c.execute('SELECT timestamp, stock FROM monitoring_history WHERE product_sku = ? ORDER BY timestamp', (sku,))
    rows = c.fetchall()
    print(f'\nStock timeline (last 15):')
    for ts, stock in rows[-15:]:
        print(f'  {ts}: {stock}')
    
    # Calculate velocity like Gold Mine does
    if len(rows) >= 2:
        total_drops = 0
        prev_stock = None
        for ts, stock in rows:
            if prev_stock is not None and stock is not None:
                diff = prev_stock - stock
                if diff > 0:
                    total_drops += diff
            prev_stock = stock
        print(f'\nTotal drops (sales): {total_drops}')
        days = 7
        velocity = total_drops / days
        print(f'Velocity (per day): {velocity:.2f}')
        if margin > 0:
            daily_profit = velocity * margin
            print(f'Daily profit: {daily_profit:.2f} MAD')
else:
    print('Product not found')

conn.close()
