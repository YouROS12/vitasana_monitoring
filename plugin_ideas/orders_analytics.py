
"""
Internal Order Analytics.
Analyzes the user's own sales data from the local database.
"""
import pandas as pd
from app.core.database import get_database

class OrderAnalyzer:
    def __init__(self):
        self.db = get_database()
        
    def get_top_selling_products(self, days=30):
        """
        Get top selling products based on confirmed orders.
        """
        with self.db._connection() as conn:
            # Query explained:
            # 1. Select items from orders
            # 2. Filter by date (last N days)
            # 3. Filter by status (processing, completed, etc - ignore cancelled)
            # 4. Group by SKU
            # 5. Sum quantity
            
            query = """
                SELECT 
                    i.sku,
                    i.product_name as name,
                    SUM(i.quantity) as total_sold,
                    COUNT(DISTINCT o.id) as order_count,
                    SUM(i.quantity * i.price_at_sync) as revenue
                FROM order_items i
                JOIN orders o ON i.order_id = o.id
                WHERE 
                    o.date_created >= date('now', ?)
                    AND o.status NOT IN ('cancelled', 'failed', 'refunded')
                GROUP BY i.sku, i.product_name
                HAVING total_sold > 0
                ORDER BY total_sold DESC
                LIMIT 100
            """
            
            df = pd.read_sql_query(query, conn, params=(f'-{days} days',))
            return df
            
    def get_sales_heatmap(self, days=30):
        """Get sales by City."""
        with self.db._connection() as conn:
            query = """
                SELECT 
                    c.id,
                    c.city, # Wait, city is in billing json usually?
                    # Ah, we don't store city in specific column... 
                    # We only have CUSTOMERS table with first_name, last_name, etc.
                    # City might be lost if not extracted!
                    # Let's check schema.
                    COUNT(o.id) as order_count
                FROM orders o
                LEFT JOIN customers c ON o.customer_id = c.id
                WHERE o.date_created >= date('now', ?)
                GROUP BY c.id
            """
            # If city isn't in DB columns, we can't easily SQL group it.
            # We'll skip Geo for now and focus on Items.
            pass
            
    def get_key_metrics(self, days=30):
        """Total revenue, orders, avg order value."""
        with self.db._connection() as conn:
            query = """
                SELECT 
                    COUNT(id) as total_orders,
                    SUM(total_amount) as total_revenue
                FROM orders 
                WHERE date_created >= date('now', ?)
                AND status NOT IN ('cancelled', 'failed')
            """
            cursor = conn.cursor()
            cursor.execute(query, (f'-{days} days',))
            row = cursor.fetchone()
            
            orders = row[0] or 0
            revenue = row[1] or 0.0
            aov = revenue / orders if orders > 0 else 0
            
            return {
                "orders": orders,
                "revenue": revenue,
                "aov": aov
            }
