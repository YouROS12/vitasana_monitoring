"""
Order Service.
Orchestrates order fetching, matching, and real-time stock checking.
"""

import logging
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# Local imports
from .client import WooCommerceClient
from .matcher import ProductMatcher
from ..core.database import get_database
from ..core.config import get_config
from ..auth.session import create_auth_session_from_config
from ..monitoring.tracker import _process_single_product

logger = logging.getLogger(__name__)


class OrderService:
    """Service to handle order synchronization and checking."""
    
    def __init__(self):
        self.config = get_config()
        self.db = get_database()
        self.client = None
        self._init_client()
        
    def _init_client(self):
        """Initialize WC client from config."""
        wc_conf = self.config.get('woocommerce', default={})
        if wc_conf.get('url') and wc_conf.get('consumer_key'):
            self.client = WooCommerceClient(
                url=wc_conf['url'],
                consumer_key=wc_conf['consumer_key'],
                consumer_secret=wc_conf['consumer_secret']
            )
        else:
            logger.warning("WooCommerce config missing")

    def sync_orders(self, status: str = 'processing', check_stock: bool = True) -> List[Dict[str, Any]]:
        """
        1. Fetch orders
        2. Match items to generic products
        3. Real-time check availability using Tracker API
        """
        if not self.client:
            return {'error': 'WooCommerce not configured'}
            
        # 1. Fetch Orders from WC
        orders = self.client.get_orders(status=status, limit=20)
        logger.info(f"Fetched {len(orders)} orders")
        
        # 2. Prepare Matcher
        db_products = self.db.get_products(limit=10000) # Get all for matching
        matcher = ProductMatcher(db_products)
        
        processed_orders = []
        
        # Collect all matched products that need stock checking
        products_to_check = {}  # sku -> product_dict
        
        for order in orders:
            order_summary = {
                'id': order['id'],
                'number': order['number'],
                'status': order['status'],
                'date_created': order['date_created'],
                'total_amount': float(order.get('total', 0)),
                'billing': order['billing'],
                'items': [],
                'fulfillability': 'unknown'
            }
            
            for item in order['line_items']:
                # Match item
                wc_sku = item.get('sku')
                wc_name = item.get('name')
                
                matched_product, match_method, score = matcher.match_item(wc_sku, wc_name)
                
                item_info = {
                    'id': item['id'],
                    'name': wc_name,
                    'sku': wc_sku,
                    'quantity': item['quantity'],
                    'match_status': 'unmatched',
                    'matched_sku': None,
                    'stock_status': 'unknown',
                    'available_qty': 0,
                    'price': 0.0
                }
                
                if matched_product:
                    item_info['match_status'] = match_method
                    item_info['matched_sku'] = matched_product['sku']
                    item_info['match_score'] = score
                    
                    # Queue for live check
                    products_to_check[matched_product['sku']] = matched_product
                
                order_summary['items'].append(item_info)
            
            processed_orders.append(order_summary)

        # 3. Real-Time Stock Check (if enabled)
        if check_stock and products_to_check:
            self._perform_live_stock_check(products_to_check)
            
            # Update order summaries with fresh data
            for order in processed_orders:
                self._update_order_status(order, products_to_check)
        
        # 4. Persist Orders and Customers
        for order in processed_orders:
            try:
                # Upsert Customer
                billing = order['billing'] or {}
                cust_id = self.db.upsert_customer(
                    id=None, # WC doesn't always give distinct customer IDs for guests
                    first_name=billing.get('first_name', ''),
                    last_name=billing.get('last_name', ''),
                    email=billing.get('email', '') or f"guest_{order['id']}@unknown.com",
                    phone=billing.get('phone', '')
                )
                
                # Update Stats
                total = float(order.get('total', 0)) # Need to ensure total is captured
                self.db.update_customer_stats(cust_id, total, order['date_created'])
                
                # Upsert Order
                # Calculate total amount if not present
                if 'total' not in order and 'items' in order:
                    total = sum(item.get('price', 0) * item.get('quantity', 0) for item in order['items'])

                self.db.upsert_order(
                    id=order['id'],
                    number=order['number'],
                    customer_id=cust_id,
                    status=order['status'],
                    date_created=order['date_created'],
                    total_amount=total,
                    fulfillability=order['fulfillability']
                )
                
                # Add Items
                self.db.add_order_items(order['id'], order['items'])
                
            except Exception as e:
                logger.error(f"Failed to persist order {order['id']}: {e}")

        return processed_orders

    def _perform_live_stock_check(self, products_map: Dict[int, Dict[str, Any]]):
        """
        Run live monitoring for the specific products found in orders.
        Updates the products_map in-place with 'latest_stock' info.
        """
        logger.info(f"Performing live stock check for {len(products_map)} unique products...")
        
        auth = create_auth_session_from_config()
        session_config = auth.get_session_config()
        
        if not session_config:
            logger.error("Auth failed for live check")
            return

        # Prepare arguments for _process_single_product
        get_url = self.config.get('api', 'get_product_url')
        filter_url = self.config.get('api', 'filter_product_url')
        timeout = self.config.get_int('api', 'timeout', default=25)
        
        # Get client_id from config
        creds = self.config.get('credentials', default=[])
        client_id = creds[0].get('client_id') if creds else ''

        # Run concurrent checks
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(
                    _process_single_product,
                    product,
                    session_config,
                    get_url,
                    filter_url,
                    client_id,
                    timeout=timeout,
                    retry_count=2
                ): sku 
                for sku, product in products_map.items()
            }
            
            for future in as_completed(futures):
                sku = futures[future]
                try:
                    result = future.result()
                    # Store result back in the map
                    if result['success']:
                        products_map[sku]['latest_stock_data'] = result
                        
                        # Also save to DB (side effect as requested)
                        self.db.add_monitoring_record(
                            sku=result['sku'],
                            stock=result['stock'],
                            price=result['price'],
                            discount_percent=result['discount'],
                            final_price=result['final_price'],
                            availability=result['availability'],
                            points=result['points']
                        )
                        self.db.update_last_checked(result['sku'])
                        
                except Exception as e:
                    logger.error(f"Error checking stock for {sku}: {e}")

    def _update_order_status(self, order: Dict[str, Any], products_map: Dict[int, Dict[str, Any]]):
        """Calculate fulfillability based on fresh stock data."""
        all_items_ready = True
        any_item_ready = False
        has_unknown = False
        
        for item in order['items']:
            matched_sku = item.get('matched_sku')
            
            if matched_sku and matched_sku in products_map:
                product_data = products_map[matched_sku]
                stock_data = product_data.get('latest_stock_data')
                
                if stock_data and stock_data.get('stock') is not None:
                    available = stock_data['stock']
                    required = item['quantity']
                    item['available_qty'] = available
                    item['price'] = stock_data.get('price')
                    
                    if available >= required:
                        item['stock_status'] = 'ready'
                        any_item_ready = True
                    elif available > 0:
                        item['stock_status'] = 'partial'
                        all_items_ready = False
                        any_item_ready = True
                    else:
                        item['stock_status'] = 'out_of_stock'
                        all_items_ready = False
                else:
                    item['stock_status'] = 'unknown' # Stock check failed or no stock field
                    has_unknown = True
                    all_items_ready = False
            else:
                item['stock_status'] = 'unmatched'
                all_items_ready = False
                has_unknown = True  # Unmatched counts as unknown fulfillability
        
        # Calculate Order Level Fulfillability
        if all_items_ready:
            order['fulfillability'] = 'ready'
        elif any_item_ready:
            order['fulfillability'] = 'partial'
        elif has_unknown: # If mostly unmatched/unknown and no confirmed stock
            order['fulfillability'] = 'unknown'
        else:
            order['fulfillability'] = 'out_of_stock'
