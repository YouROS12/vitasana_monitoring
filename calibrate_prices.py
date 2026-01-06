
"""
Price Calibration Script.
Finds products with missing "Buying Price" (final_price) and fetches them from the Detail API.
Run this periodically or once to fix "0 MAD" prices in Gold Mine.
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

def get_missing_price_skus(db):
    """Find SKUs that have never had a valid final_price."""
    # Logic: Get all SKUs, check if they have ANY history record with final_price > 0
    # or just check the latest status.
    
    # Efficient query: Products EXCEPT Products with known price
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
    config = get_config()
    auth = create_auth_session_from_config()
    
    logger.info("Checking for products with missing prices...")
    products = get_missing_price_skus(db)
    
    if not products:
        logger.info("✅ All products have pricing data. No calibration needed.")
        return

    logger.info(f"🔍 Found {len(products)} products with missing prices.")
    logger.info("Starting calibration (this may take time)...")

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
    # Be gentle with the API
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
