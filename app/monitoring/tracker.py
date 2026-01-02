"""
Product monitoring via API.
Tracks stock levels, prices, and availability using authenticated API calls.
"""

import requests
import logging
import threading
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from datetime import datetime, timezone

from ..core.database import get_database
from ..auth.session import AuthSession, SessionConfig, create_auth_session_from_config

logger = logging.getLogger(__name__)


@dataclass
class MonitoringProgress:
    """Progress tracking for monitoring process."""
    total_products: int = 0
    products_processed: int = 0
    products_updated: int = 0
    products_failed: int = 0
    is_running: bool = False
    current_phase: str = ""
    error: Optional[str] = None


# Global progress tracker
_progress = MonitoringProgress()


def get_progress() -> MonitoringProgress:
    """Get current monitoring progress."""
    return _progress


def _parse_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Safely parse a float value."""
    if value is None:
        return default
    try:
        if isinstance(value, str):
            # Remove currency symbols and whitespace
            value = re.sub(r'[^\d.,\-]', '', value)
            value = value.replace(',', '.')
        return float(value)
    except (ValueError, TypeError):
        return default


def _parse_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """Safely parse an integer value."""
    if value is None:
        return default
    try:
        if isinstance(value, str):
            value = re.sub(r'[^\d\-]', '', value)
        return int(float(value))
    except (ValueError, TypeError):
        return default


def _process_single_product(
    product: Dict[str, Any],
    session_config: SessionConfig,
    get_product_url: str,
    filter_product_url: str,
    client_id: str,
    timeout: int,
    retry_count: int = 3,
    retry_delay: float = 2.0
) -> Dict[str, Any]:
    """
    Process a single product: fetch API data and extract monitoring info.
    Uses GET requests with product_id/client_id params like the old app.
    
    Returns:
        Dict with keys: sku, success, stock, price, discount, final_price, availability, points, error
    """
    thread_id = threading.get_ident()
    sku = product['sku']
    name = product.get('name', '')
    
    result = {
        'sku': sku,
        'success': False,
        'stock': None,
        'price': None,
        'discount': None,
        'final_price': None,
        'availability': None,
        'points': None,
        'error': None
    }
    
    # Create thread-local session using config from auth
    session = requests.Session()
    session.auth = session_config.auth  # HTTP Basic Auth (username, password)
    session.headers.update(session_config.headers)
    session.headers.update({
        'X-Requested-With': 'XMLHttpRequest',
    })
    session.cookies.update(session_config.cookies)
    
    logger.info(f"[{thread_id}] Processing SKU {sku}: {name[:40]}...")
    
    # ============ STEP 1: Get price/discount/availability from get_product API ============
    for attempt in range(retry_count):
        try:
            # Use GET with params like the old app
            params = {
                'product_id': str(sku),
                'client_id': client_id
            }
            
            response = session.get(
                get_product_url,
                params=params,
                timeout=timeout
            )
            
            logger.info(f"[{thread_id}] SKU {sku}: get_product status={response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.debug(f"[{thread_id}] SKU {sku}: get_product response: {data}")
                
                if data and isinstance(data, dict):
                    # Extract data - map API fields to our schema
                    # API returns: regular_price, stock_1, actif, etc.
                    result['price'] = _parse_float(data.get('regular_price') or data.get('price'))
                    result['discount'] = _parse_float(data.get('discount'))
                    result['final_price'] = _parse_float(data.get('final_price') or data.get('regular_price'))
                    result['stock'] = _parse_int(data.get('stock_1') or data.get('stock'))
                    
                    # Availability: check 'actif' field or 'available'
                    actif = data.get('actif')
                    if actif is not None:
                        result['availability'] = "Disponible" if str(actif) == "1" else "Indisponible"
                    else:
                        result['availability'] = data.get('available')
                    
                    result['points'] = _parse_int(data.get('points'))
                    
                    logger.info(f"[{thread_id}] SKU {sku}: price={result['price']}, stock={result['stock']}")
                    break  # Success, exit retry loop
                else:
                    logger.warning(f"[{thread_id}] SKU {sku}: Invalid get_product response")
                    
            elif response.status_code in [401, 403]:
                result['error'] = f"Authentication failed ({response.status_code})"
                logger.warning(f"[{thread_id}] SKU {sku}: Auth error {response.status_code}")
                return result
            else:
                logger.warning(f"[{thread_id}] SKU {sku}: get_product status {response.status_code}")
                
        except requests.exceptions.Timeout:
            logger.warning(f"[{thread_id}] SKU {sku}: get_product timeout (attempt {attempt + 1})")
        except Exception as e:
            logger.warning(f"[{thread_id}] SKU {sku}: get_product error - {e}")
        
        if attempt < retry_count - 1:
            import time
            time.sleep(retry_delay)
    
    # ============ STEP 2: Get stock from filter_product API ============
    if filter_product_url and name:
        # Try name variants like the old app
        name_variants = [name]
        
        # Simplified name (before dash)
        if ' – ' in name:
            name_variants.append(name.split(' – ')[0].strip())
        elif ' - ' in name:
            name_variants.append(name.split(' - ')[0].strip())
        
        # First 3 words
        words = re.split(r'\s+|-|–', name)
        words = [w for w in words if w]
        if len(words) >= 3:
            name_variants.append(' '.join(words[:3]))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_variants = []
        for v in name_variants:
            if v not in seen:
                seen.add(v)
                unique_variants.append(v)
        
        for variant in unique_variants:
            try:
                response = session.get(
                    filter_product_url,
                    params={'title': variant},
                    timeout=timeout
                )
                
                if response.status_code == 200:
                    stock_data = response.json()
                    
                    if isinstance(stock_data, list):
                        for item in stock_data:
                            item_sku = item.get('sku') or item.get('id')
                            if str(item_sku) == str(sku):
                                result['stock'] = _parse_int(item.get('stock_1') or item.get('stock'))
                                logger.info(f"[{thread_id}] SKU {sku}: stock={result['stock']} (via '{variant}')")
                                break
                    
                    if result['stock'] is not None:
                        break  # Found stock, exit variant loop
                        
            except Exception as e:
                logger.debug(f"[{thread_id}] SKU {sku}: filter_product error for '{variant}': {e}")
    
    # Mark as success if we got at least price or stock
    if result['final_price'] is not None or result['stock'] is not None:
        result['success'] = True
    else:
        result['error'] = "Could not fetch product data"
    
    return result


def run_monitoring(
    auth_session: AuthSession,
    get_product_url: str,
    filter_product_url: str,
    client_id: str,
    timeout: int = 25,
    limit: Optional[int] = None,
    offset: int = 0,
    keywords: Optional[List[str]] = None,
    workers: int = 5,
    retry_count: int = 3,
    progress_callback: Optional[Callable[[MonitoringProgress], None]] = None,
    stop_event: Optional[threading.Event] = None
) -> MonitoringProgress:
    """
    Run the product monitoring process.
    
    Args:
        auth_session: Authenticated session manager
        get_product_url: URL for get_product API
        filter_product_url: URL for filter_product API
        timeout: Request timeout
        limit: Max products to process
        offset: Pagination offset
        keywords: Filter products by keywords
        workers: Number of concurrent workers
        retry_count: Retries per product
        progress_callback: Optional progress callback
        stop_event: Optional threading.Event to signal stop
    
    Returns:
        MonitoringProgress with final results
    """
    global _progress
    
    _progress = MonitoringProgress(
        is_running=True,
        current_phase="Initializing"
    )
    
    def update_progress():
        if progress_callback:
            progress_callback(_progress)
    
    def should_stop():
        return stop_event and stop_event.is_set()
    
    try:
        # Get session config for thread-safe use
        _progress.current_phase = "Authenticating"
        update_progress()
        
        if should_stop():
            _progress.current_phase = "Stopped by user"
            _progress.is_running = False
            return _progress
        
        session_config = auth_session.get_session_config()
        if session_config is None:
            _progress.error = "Authentication failed"
            _progress.is_running = False
            _progress.current_phase = "Failed"
            update_progress()
            return _progress
        
        # Get products from database
        _progress.current_phase = "Loading products"
        update_progress()
        
        db = get_database()
        products = db.get_products(limit=limit, offset=offset, keywords=keywords)
        
        _progress.total_products = len(products)
        logger.info(f"Monitoring {len(products)} products")
        
        if not products:
            _progress.current_phase = "Complete - no products"
            _progress.is_running = False
            update_progress()
            return _progress
        
        if should_stop():
            _progress.current_phase = "Stopped by user"
            _progress.is_running = False
            return _progress
        
        # Process products concurrently
        _progress.current_phase = "Monitoring products"
        update_progress()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _process_single_product,
                    product,
                    session_config,
                    get_product_url,
                    filter_product_url,
                    client_id,
                    timeout,
                    retry_count
                ): product
                for product in products
            }
            
            for future in as_completed(futures):
                if should_stop():
                    logger.info("Stop requested, cancelling remaining tasks...")
                    for f in futures:
                        f.cancel()
                    break
                
                product = futures[future]
                _progress.products_processed += 1
                
                try:
                    result = future.result()
                    
                    if result['success']:
                        # Save monitoring record
                        db.add_monitoring_record(
                            sku=result['sku'],
                            stock=result['stock'],
                            price=result['price'],
                            discount_percent=result['discount'],
                            final_price=result['final_price'],
                            availability=result['availability'],
                            points=result['points'],
                            timestamp=timestamp
                        )
                        db.update_last_checked(result['sku'], timestamp)
                        _progress.products_updated += 1
                    else:
                        _progress.products_failed += 1
                        
                except Exception as e:
                    logger.error(f"Error processing SKU {product['sku']}: {e}")
                    _progress.products_failed += 1
                
                update_progress()
        
        _progress.current_phase = "Stopped by user" if should_stop() else "Complete"
        _progress.is_running = False
        update_progress()
        
        logger.info(f"Monitoring complete: {_progress.products_updated} updated, {_progress.products_failed} failed")
        
        return _progress
        
    except Exception as e:
        logger.exception("Monitoring failed")
        _progress.error = str(e)
        _progress.is_running = False
        _progress.current_phase = "Failed"
        update_progress()
        return _progress


def run_monitoring_from_config(
    limit: Optional[int] = None,
    offset: int = 0,
    keywords: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[MonitoringProgress], None]] = None
) -> MonitoringProgress:
    """Run monitoring using settings from config file."""
    from ..core.config import get_config
    
    config = get_config()
    auth = create_auth_session_from_config()
    
    return run_monitoring(
        auth_session=auth,
        get_product_url=config.get('api', 'get_product_url'),
        filter_product_url=config.get('api', 'filter_product_url'),
        timeout=config.get_int('api', 'timeout', default=25),
        limit=limit,
        offset=offset,
        keywords=keywords,
        workers=config.get_int('workers', 'monitoring', default=5),
        retry_count=config.get_int('api', 'retry_count', default=3),
        progress_callback=progress_callback
    )
