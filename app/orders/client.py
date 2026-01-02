"""
WooCommerce API Client.
Handles fetching orders from the WooCommerce store.
"""

import requests
import logging
from typing import List, Dict, Optional, Any
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class WooCommerceClient:
    """Client for WooCommerce REST API."""
    
    def __init__(self, url: str, consumer_key: str, consumer_secret: str):
        self.base_url = url.rstrip('/') + '/wp-json/wc/v3/'
        self.auth = (consumer_key, consumer_secret)
        self.session = requests.Session()
    
    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Make GET request to WC API."""
        url = urljoin(self.base_url, endpoint)
        try:
            response = self.session.get(
                url, 
                auth=self.auth, 
                params=params, 
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"WooCommerce API error: {e}")
            return None
    
    def get_orders(self, status: str = 'processing', limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch orders with specific status.
        
        Args:
            status: Order status filter (processing, pending, on-hold, etc.)
            limit: Max records to return
            
        Returns:
            List of order dictionaries
        """
        logger.info(f"Fetching {status} orders from WooCommerce...")
        
        params = {
            'status': status,
            'per_page': limit,
            'orderby': 'date',
            'order': 'desc'
        }
        
        orders = self._get('orders', params)
        if orders is None:
            return []
            
        logger.info(f"Retrieved {len(orders)} orders")
        return orders
    
    def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        """Fetch single order."""
        return self._get(f"orders/{order_id}")
