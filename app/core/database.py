"""
Database operations for Vitasana Monitoring.
Uses SQLite for storage.
"""

import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Table and column names
PRODUCTS_TABLE = "products"
HISTORY_TABLE = "monitoring_history"
CUSTOMERS_TABLE = "customers"
ORDERS_TABLE = "orders"
ORDER_ITEMS_TABLE = "order_items"


class Database:
    """SQLite database manager."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_tables()
    
    @contextmanager
    def _connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _ensure_tables(self) -> None:
        """Create tables if they don't exist."""
        with self._connection() as conn:
            cursor = conn.cursor()
            
            # Products table
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {PRODUCTS_TABLE} (
                    sku INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    product_url TEXT,
                    image_url TEXT,
                    description TEXT,
                    discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_checked_at TEXT
                )
            """)
            
            # Monitoring history table
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_sku INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    stock INTEGER,
                    price REAL,
                    discount_percent REAL,
                    final_price REAL,
                    availability TEXT,
                    points INTEGER,
                    FOREIGN KEY (product_sku) REFERENCES {PRODUCTS_TABLE}(sku)
                )
            """)
            
            # Index for faster history queries
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_history_sku_time 
                ON {HISTORY_TABLE}(product_sku, timestamp DESC)
            """)
            
            # Customers table
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {CUSTOMERS_TABLE} (
                    id INTEGER PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    email TEXT UNIQUE,
                    phone TEXT,
                    total_spent REAL DEFAULT 0,
                    order_count INTEGER DEFAULT 0,
                    last_order_date TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Orders table
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {ORDERS_TABLE} (
                    id INTEGER PRIMARY KEY,
                    number TEXT,
                    customer_id INTEGER,
                    status TEXT,
                    date_created TEXT,
                    total_amount REAL,
                    fulfillability TEXT,
                    sync_timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES {CUSTOMERS_TABLE}(id)
                )
            """)
            
            # Order items table
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {ORDER_ITEMS_TABLE} (
                    id INTEGER PRIMARY KEY,
                    order_id INTEGER,
                    product_name TEXT,
                    sku TEXT,
                    quantity INTEGER,
                    matched_sku INTEGER,
                    match_type TEXT,
                    stock_status TEXT,
                    available_qty INTEGER,
                    price_at_sync REAL,
                    FOREIGN KEY (order_id) REFERENCES {ORDERS_TABLE}(id),
                    FOREIGN KEY (matched_sku) REFERENCES {PRODUCTS_TABLE}(sku)
                )
            """)

            # Scan Prefixes table (Mass Scanner Optimization)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS scan_prefixes (
                    prefix TEXT PRIMARY KEY,
                    result_count INTEGER,
                    last_scanned_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            logger.info(f"Database initialized at {self.db_path}")
    
    # ==================== Product Operations ====================
    
    def add_product(
        self,
        sku: int,
        name: str,
        product_url: Optional[str] = None,
        image_url: Optional[str] = None,
        description: Optional[str] = None
    ) -> bool:
        """
        Add a new product to the database.
        Returns True if added, False if already exists.
        """
        with self._connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(f"""
                    INSERT INTO {PRODUCTS_TABLE} (sku, name, product_url, image_url, description)
                    VALUES (?, ?, ?, ?, ?)
                """, (sku, name, product_url, image_url, description))
                logger.debug(f"Added product: {sku} - {name}")
                return True
            except sqlite3.IntegrityError:
                logger.debug(f"Product already exists: {sku}")
                return False
    
    def get_all_skus(self) -> set:
        """Get all product SKUs as a set."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT sku FROM {PRODUCTS_TABLE}")
            return {row['sku'] for row in cursor.fetchall()}
    
    def get_products(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        keywords: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get products with optional filtering.
        
        Args:
            limit: Max number of products to return
            offset: Pagination offset
            keywords: Filter by name/SKU containing any keyword
        """
        with self._connection() as conn:
            cursor = conn.cursor()
            
            query = f"SELECT * FROM {PRODUCTS_TABLE}"
            params = []
            
            # Keyword filtering
            if keywords:
                conditions = []
                for kw in keywords:
                    conditions.append("(name LIKE ? OR CAST(sku AS TEXT) LIKE ?)")
                    params.extend([f"%{kw}%", f"%{kw}%"])
                query += " WHERE " + " OR ".join(conditions)
            
            query += " ORDER BY sku"
            
            if limit:
                query += f" LIMIT {limit} OFFSET {offset}"
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_product(self, sku: int) -> Optional[Dict[str, Any]]:
        """Get a single product by SKU."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {PRODUCTS_TABLE} WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_last_checked(self, sku: int, timestamp: Optional[str] = None) -> None:
        """Update the last_checked_at timestamp for a product."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
        
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE {PRODUCTS_TABLE} SET last_checked_at = ? WHERE sku = ?
            """, (timestamp, sku))
    
    def get_product_count(self) -> int:
        """Get total number of products."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) as count FROM {PRODUCTS_TABLE}")
            return cursor.fetchone()['count']
    
    # ==================== Monitoring History Operations ====================
    
    def add_monitoring_record(
        self,
        sku: int,
        stock: Optional[int] = None,
        price: Optional[float] = None,
        discount_percent: Optional[float] = None,
        final_price: Optional[float] = None,
        availability: Optional[str] = None,
        points: Optional[int] = None,
        timestamp: Optional[str] = None
    ) -> int:
        """
        Add a monitoring record.
        Returns the record ID.
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
        
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                INSERT INTO {HISTORY_TABLE} 
                (product_sku, timestamp, stock, price, discount_percent, final_price, availability, points)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (sku, timestamp, stock, price, discount_percent, final_price, availability, points))
            
            return cursor.lastrowid
    
    def get_last_record(self, sku: int) -> Optional[Dict[str, Any]]:
        """Get the most recent monitoring record for a product."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT * FROM {HISTORY_TABLE} 
                WHERE product_sku = ? 
                ORDER BY timestamp DESC 
                LIMIT 1
            """, (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_product_history(
        self,
        sku: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get monitoring history for a product."""
        with self._connection() as conn:
            cursor = conn.cursor()
            
            query = f"SELECT * FROM {HISTORY_TABLE} WHERE product_sku = ?"
            params = [sku]
            
            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)
            
            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)
            
            query += " ORDER BY timestamp DESC"
            
            if limit:
                query += f" LIMIT {limit}"
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_full_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get all history records for the last N hours."""
        import datetime
        start_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).isoformat()
        
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT h.*, p.name 
                FROM {HISTORY_TABLE} h
                JOIN {PRODUCTS_TABLE} p ON h.product_sku = p.sku
                WHERE h.timestamp >= ?
                ORDER BY h.timestamp ASC
            """, (start_time,))
            return [dict(row) for row in cursor.fetchall()]

    def get_latest_statuses(self) -> List[Dict[str, Any]]:
        """Get the latest monitoring record for each product."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT p.*, h.stock, h.price, h.discount_percent, h.final_price, 
                       h.availability, h.points, h.timestamp as last_monitored
                FROM {PRODUCTS_TABLE} p
                LEFT JOIN (
                    SELECT product_sku, stock, price, discount_percent, final_price, 
                           availability, points, timestamp,
                           ROW_NUMBER() OVER (PARTITION BY product_sku ORDER BY timestamp DESC) as rn
                    FROM {HISTORY_TABLE}
                ) h ON p.sku = h.product_sku AND h.rn = 1
                ORDER BY p.name
            """)
            return [dict(row) for row in cursor.fetchall()]


# Global database instance

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
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # ==================== Mass Scanner Operations ====================

    def record_scan_prefix(self, prefix: str, count: int):
        """Record a prefix that returned results."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO scan_prefixes (prefix, result_count, last_scanned_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (prefix, count))

    def get_effective_prefixes(self) -> List[str]:
        """Get list of prefixes that historically returned results."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT prefix FROM scan_prefixes ORDER BY prefix")
            return [row['prefix'] for row in cursor.fetchall()]

    def upsert_product_from_search(self, data: Dict[str, Any]) -> bool:
        """
        Upsert a product from Mass Scanner search result.
        Maps fields correctly (stock_1 -> stock).
        """
        sku = int(data.get('sku') or data.get('id'))
        name = data.get('name', 'Unknown')
        image = data.get('images', None)
        desc = data.get('description', None)
        
        # Parse stock and price
        stock = int(data.get('stock_1', 0))
        price = float(data.get('regular_price', 0))
        
        with self._connection() as conn:
            cursor = conn.cursor()
            
            # Upsert Product
            cursor.execute(f"""
                INSERT INTO {PRODUCTS_TABLE} (sku, name, image_url, description, last_checked_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(sku) DO UPDATE SET
                    name=excluded.name,
                    image_url=excluded.image_url,
                    description=excluded.description,
                    last_checked_at=CURRENT_TIMESTAMP
            """, (sku, name, image, desc))
            
            # Record History
            cursor.execute(f"""
                INSERT INTO {HISTORY_TABLE} 
                (product_sku, timestamp, stock, price, availability)
                VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?)
            """, (sku, stock, price, 'In Stock' if stock > 0 else 'Out of Stock'))
            
            return True
_db_instance: Optional[Database] = None


def get_database(db_path: Optional[Path] = None) -> Database:
    """Get the global database instance."""
    global _db_instance
    if _db_instance is None:
        if db_path is None:
            from .config import get_config
            db_path = get_config().db_path
        _db_instance = Database(db_path)
    return _db_instance
