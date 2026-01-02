
    # ==================== Order & Customer Operations ====================

    def upsert_customer(
        self,
        id: Optional[int],
        first_name: str,
        last_name: str,
        email: str,
        phone: str = ""
    ) -> int:
        """Create or update a customer."""
        with self._connection() as conn:
            cursor = conn.cursor()
            
            # Try to find by email if ID is missing (new customer)
            if not id and email:
                cursor.execute(f"SELECT id FROM {CUSTOMERS_TABLE} WHERE email = ?", (email,))
                row = cursor.fetchone()
                if row:
                    id = row['id']
            
            if id:
                cursor.execute(f"""
                    UPDATE {CUSTOMERS_TABLE} 
                    SET first_name=?, last_name=?, email=?, phone=?
                    WHERE id=?
                """, (first_name, last_name, email, phone, id))
                return id
            else:
                cursor.execute(f"""
                    INSERT INTO {CUSTOMERS_TABLE} (first_name, last_name, email, phone)
                    VALUES (?, ?, ?, ?)
                """, (first_name, last_name, email, phone))
                return cursor.lastrowid

    def update_customer_stats(self, customer_id: int, total_spent: float, order_date: str):
        """Update customer spending stats."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE {CUSTOMERS_TABLE}
                SET total_spent = total_spent + ?,
                    order_count = order_count + 1,
                    last_order_date = MAX(last_order_date, ?)
                WHERE id = ?
            """, (total_spent, order_date, customer_id))

    def upsert_order(
        self,
        id: int,
        number: str,
        customer_id: int,
        status: str,
        date_created: str,
        total_amount: float,
        fulfillability: str
    ) -> bool:
        """Insert or update an order."""
        with self._connection() as conn:
            cursor = conn.cursor()
            
            # Check if exists
            cursor.execute(f"SELECT id FROM {ORDERS_TABLE} WHERE id = ?", (id,))
            exists = cursor.fetchone()
            
            if exists:
                cursor.execute(f"""
                    UPDATE {ORDERS_TABLE}
                    SET status=?, fulfillability=?, sync_timestamp=CURRENT_TIMESTAMP
                    WHERE id=?
                """, (status, fulfillability, id))
                return False  # Updated
            else:
                cursor.execute(f"""
                    INSERT INTO {ORDERS_TABLE} 
                    (id, number, customer_id, status, date_created, total_amount, fulfillability)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (id, number, customer_id, status, date_created, total_amount, fulfillability))
                return True  # Inserted

    def add_order_items(self, order_id: int, items: List[Dict[str, Any]]):
        """Add line items for an order (clears existing first)."""
        with self._connection() as conn:
            cursor = conn.cursor()
            # Clear existing items for this order to avoid dups/stale
            cursor.execute(f"DELETE FROM {ORDER_ITEMS_TABLE} WHERE order_id = ?", (order_id,))
            
            for item in items:
                cursor.execute(f"""
                    INSERT INTO {ORDER_ITEMS_TABLE}
                    (id, order_id, product_name, sku, quantity, matched_sku, match_type, 
                     stock_status, available_qty, price_at_sync)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item['id'], order_id, item['name'], item['sku'], item['quantity'],
                    item.get('matched_sku'), item.get('match_status'), item.get('stock_status'),
                    item.get('available_qty'), item.get('price')
                ))

    def get_orders(self, limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get stored orders."""
        with self._connection() as conn:
            cursor = conn.cursor()
            query = f"""
                SELECT o.*, c.first_name, c.last_name, c.email 
                FROM {ORDERS_TABLE} o
                LEFT JOIN {CUSTOMERS_TABLE} c ON o.customer_id = c.id
            """
            params = []
            
            if status:
                query += " WHERE o.status = ?"
                params.append(status)
            
            query += " ORDER BY o.date_created DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            orders = [dict(row) for row in cursor.fetchall()]
            
            # Attach items
            for order in orders:
                cursor.execute(f"SELECT * FROM {ORDER_ITEMS_TABLE} WHERE order_id = ?", (order['id'],))
                order['items'] = [dict(row) for row in cursor.fetchall()]
                
            return orders

    def get_customers(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get top customers."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT * FROM {CUSTOMERS_TABLE} 
                ORDER BY total_spent DESC 
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
