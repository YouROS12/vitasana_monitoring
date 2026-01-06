
"""
Price Calibration Script.
1. FAST: Repairs '0 MAD' prices by copying data from older history records.
2. SLOW: Fetches missing prices from the API for products that have NO history.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.core.database import get_database, HISTORY_TABLE, PRODUCTS_TABLE
from app.auth.session import create_auth_session_from_config
from app.monitoring.tracker import _process_single_product
from app.core.config import get_config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def repair_from_history(db):
    """
    Repair latest records that have missing price by looking at older records.
    Returns count of fixed records.
    """
    logger.info("🔧 Attempting to repair prices from history...")
    
    with db._connection() as conn:
        cursor = conn.cursor()
        
        # 1. Get all SKUs with latest price = 0 or NULL
        # querying latest record for each SKU
        cursor.execute(f"""
            WITH Latest AS (
                SELECT product_sku, timestamp,
                       ROW_NUMBER() OVER (PARTITION BY product_sku ORDER BY timestamp DESC) as rn
                FROM {HISTORY_TABLE}
            )
            SELECT product_sku, timestamp 
            FROM Latest 
            WHERE rn = 1 
            AND product_sku IN (
                SELECT product_sku FROM {HISTORY_TABLE} 
                GROUP BY product_sku 
                HAVING MAX(final_price) > 0  -- Only try if there is valid history
            )
        """)
        
        candidates = cursor.fetchall()
        logger.info(f"Found {len(candidates)} products with valid history but broken latest status.")
        
        fixed_count = 0
        
        for sku, latest_ts in candidates:
            # Find last GOOD price
            cursor.execute(f"""
                SELECT final_price, price, discount_percent 
                FROM {HISTORY_TABLE}
                WHERE product_sku = ? AND final_price > 0
                ORDER BY timestamp DESC
                LIMIT 1
            """, (sku,))
            
            good_data = cursor.fetchone()
            
            if good_data:
                # Update the BAD latest record
                cursor.execute(f"""
                    UPDATE {HISTORY_TABLE}
                    SET final_price = ?,
                        price = ?,
                        discount_percent = ?
                    WHERE product_sku = ? AND timestamp = ?
                """, (good_data['final_price'], good_data['price'], good_data['discount_percent'], sku, latest_ts))
                fixed_count += 1
                
        conn.commit()
        return fixed_count

def get_missing_price_skus(db):
    """Find SKUs that have NEVER had a valid final_price."""
    query = f"""
        SELECT sku, name FROM {PRODUCTS_TABLE}
        WHERE sku NOT IN (
            SELECT DISTINCT product_sku 
            FROM {HISTORY_TABLE} 
            WHERE final_price > 0
        )
    """
    with db._connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        return [{"sku": row[0], "name": row[1]} for row in cursor.fetchall()]

def calibrate():
    db = get_database()
    
    # PHASE 1: REPAIR FROM DB (Instant)
    repaired = repair_from_history(db)
    logger.info(f"✅ Repaired {repaired} products using history data.")
    
    # PHASE 2: API FETCH (Slow, for completely new/never-scanned items)
    config = get_config()
    auth = create_auth_session_from_config()
    
    products = get_missing_price_skus(db)
    
    if not products:
        logger.info("✅ All products have pricing data. finished.")
        return

    logger.info(f"🔍 Found {len(products)} products that have NEVER been priced. Fetching from API...")
    
    # Auth
    session_config = auth.get_session_config()
    if not session_config:
        logger.error("❌ Authentication failed. Check config.")
        return

    # API Config
    get_url = config.get('api', 'get_product_url')
    filter_url = config.get('api', 'filter_product_url')
    timeout = config.get_int('api', 'timeout', default=25)
    creds = config.get('credentials', default=[])
    client_id = creds[0].get('client_id') if creds else ''

    # Progress stats
    total = len(products)
    processed = 0
    updated = 0
    failed = 0
    
    # Thread Pool
    max_workers = 3 
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _process_single_product,
                p,
                session_config,
                get_url,
                filter_url,
                client_id,
                timeout,
                retry_count=2
            ): p
            for p in products
        }
        
        for future in as_completed(futures):
            p = futures[future]
            processed += 1
            
            try:
                result = future.result()
                if result['success'] and result['final_price'] is not None:
                    # Save to DB
                    db.add_monitoring_record(
                        sku=result['sku'],
                        stock=result['stock'],
                        price=result['price'],
                        discount_percent=result['discount'],
                        final_price=result['final_price'],
                        availability=result['availability'],
                        points=result['points']
                    )
                    db.update_last_checked(result['sku'])
                    updated += 1
                    logger.info(f"[{processed}/{total}] ✅ Fixed {p['name']} -> {result['final_price']} MAD")
                else:
                    failed += 1
                    logger.warning(f"[{processed}/{total}] ⚠️ Failed to get price for {p['name']}")
                    
            except Exception as e:
                failed += 1
                logger.error(f"Error processing {p['sku']}: {e}")

    logger.info(f"Calibration Complete. Updated: {updated}, Failed: {failed}")

if __name__ == "__main__":
    calibrate()
