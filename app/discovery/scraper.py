"""
Product discovery via web scraping.
Scrapes the public pharmacy website to find new products.
"""

import requests
from bs4 import BeautifulSoup
import logging
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass

from ..core.database import get_database

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryProgress:
    """Progress tracking for discovery process."""
    total_pages: int = 0
    pages_scanned: int = 0
    products_found: int = 0
    products_added: int = 0
    is_running: bool = False
    current_phase: str = ""
    error: Optional[str] = None
    newly_added_skus: List[int] = None  # Track SKUs added for auto-sync
    
    def __post_init__(self):
        if self.newly_added_skus is None:
            self.newly_added_skus = []


# Global progress tracker
_progress = DiscoveryProgress()


def get_progress() -> DiscoveryProgress:
    """Get current discovery progress."""
    return _progress


def _fetch_listing_page(
    page_num: int,
    base_url: str,
    user_agents: List[str],
    timeout: int
) -> Optional[Dict[int, dict]]:
    """
    Fetch and parse a single listing page.
    Returns dict of {sku: product_info} or None if no products found.
    """
    thread_id = threading.get_ident()
    page_url = f"{base_url.rstrip('/')}/page/{page_num}/" if page_num > 1 else base_url
    
    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    
    try:
        logger.debug(f"[{thread_id}] Scanning page {page_num}...")
        response = requests.get(page_url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'lxml')
        product_elements = soup.find_all('div', class_='klb-product')
        
        if not product_elements:
            logger.info(f"[{thread_id}] No products on page {page_num}")
            return None
        
        products = {}
        for el in product_elements:
            name_tag = el.select_one('div.product-text h4 a')
            sku_tag = el.select_one('a.ajax_add_to_cart')
            
            if not name_tag or not sku_tag:
                continue
            
            sku_str = sku_tag.get('data-product_sku', '').strip()
            if not sku_str:
                continue
            
            try:
                sku = int(sku_str)
            except ValueError:
                continue
            
            name = name_tag.text.strip()
            url = name_tag.get('href', '')
            
            img_tag = el.select_one('div.product-02-img img')
            img_url = None
            if img_tag:
                img_url = img_tag.get('data-src') or img_tag.get('data-lazy-src') or img_tag.get('src')
            
            products[sku] = {
                'sku': sku,
                'name': name,
                'url': url,
                'img_url': img_url
            }
        
        return products
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.info(f"[{thread_id}] Page {page_num} not found (end of listings)")
            return None
        logger.error(f"[{thread_id}] HTTP error on page {page_num}: {e}")
    except Exception as e:
        logger.error(f"[{thread_id}] Error on page {page_num}: {e}")
    
    return {}  # Empty dict on error (different from None which signals end)


def _fetch_description(
    product: dict,
    user_agents: List[str],
    timeout: int
) -> dict:
    """Fetch product description from product page."""
    thread_id = threading.get_ident()
    url = product.get('url', '')
    
    if not url:
        product['description'] = None
        return product
    
    headers = {'User-Agent': random.choice(user_agents)}
    
    try:
        logger.debug(f"[{thread_id}] Fetching description for SKU {product['sku']}")
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'lxml')
        desc_panel = soup.find('div', id='tab-description')
        
        if desc_panel:
            paragraphs = desc_panel.find_all('p')
            description = '\n'.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
            product['description'] = description
        else:
            product['description'] = None
            
    except Exception as e:
        logger.error(f"[{thread_id}] Error fetching description for SKU {product['sku']}: {e}")
        product['description'] = None
    
    return product


def run_discovery(
    base_url: str,
    start_page: int = 1,
    end_page: int = 100,
    user_agents: List[str] = None,
    timeout: int = 30,
    listing_workers: int = 4,
    description_workers: int = 8,
    progress_callback: Optional[Callable[[DiscoveryProgress], None]] = None,
    stop_event: Optional[threading.Event] = None
) -> DiscoveryProgress:
    """
    Run the full product discovery process.
    
    Args:
        base_url: Shop base URL
        start_page: First page to scan
        end_page: Last page to scan
        user_agents: List of User-Agent strings to rotate
        timeout: Request timeout in seconds
        listing_workers: Concurrent workers for listing pages
        description_workers: Concurrent workers for descriptions
        progress_callback: Optional callback for progress updates
        stop_event: Optional threading.Event to signal stop
    
    Returns:
        DiscoveryProgress with final results
    """
    global _progress
    
    if user_agents is None:
        user_agents = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0"]
    
    _progress = DiscoveryProgress(
        total_pages=end_page - start_page + 1,
        is_running=True,
        current_phase="Initializing"
    )
    
    def update_progress():
        if progress_callback:
            progress_callback(_progress)
    
    def should_stop():
        return stop_event and stop_event.is_set()
    
    try:
        # Get existing SKUs from database
        db = get_database()
        existing_skus = db.get_all_skus()
        logger.info(f"Found {len(existing_skus)} existing products in database")
        
        if should_stop():
            _progress.current_phase = "Stopped by user"
            _progress.is_running = False
            return _progress
        
        # Phase 1: Scan listing pages
        _progress.current_phase = "Scanning listing pages"
        update_progress()
        
        all_products = {}
        
        with ThreadPoolExecutor(max_workers=listing_workers) as executor:
            futures = {
                executor.submit(_fetch_listing_page, page, base_url, user_agents, timeout): page
                for page in range(start_page, end_page + 1)
            }
            
            for future in as_completed(futures):
                if should_stop():
                    logger.info("Stop requested, cancelling remaining tasks...")
                    for f in futures:
                        f.cancel()
                    _progress.current_phase = "Stopped by user"
                    _progress.is_running = False
                    return _progress
                
                page_num = futures[future]
                _progress.pages_scanned += 1
                
                try:
                    result = future.result()
                    if result is None:  # End of listings
                        logger.info(f"Page {page_num} signaled end of listings")
                    elif result:
                        all_products.update(result)
                        _progress.products_found = len(all_products)
                except Exception as e:
                    logger.error(f"Page {page_num} error: {e}")
                
                update_progress()
        
        logger.info(f"Phase 1 complete: Found {len(all_products)} products")
        
        if should_stop():
            _progress.current_phase = "Stopped by user"
            _progress.is_running = False
            return _progress
        
        # Filter to new products only
        new_products = [p for sku, p in all_products.items() if sku not in existing_skus]
        
        if not new_products:
            logger.info("No new products to add")
            _progress.current_phase = "Complete - no new products"
            _progress.is_running = False
            update_progress()
            return _progress
        
        logger.info(f"Found {len(new_products)} new products to process")
        
        # Phase 2: Fetch descriptions
        _progress.current_phase = f"Fetching descriptions ({len(new_products)} products)"
        update_progress()
        
        products_with_descriptions = []
        
        with ThreadPoolExecutor(max_workers=description_workers) as executor:
            futures = {
                executor.submit(_fetch_description, product, user_agents, timeout): product
                for product in new_products
            }
            
            for future in as_completed(futures):
                if should_stop():
                    logger.info("Stop requested during description fetch...")
                    for f in futures:
                        f.cancel()
                    break
                
                try:
                    result = future.result()
                    products_with_descriptions.append(result)
                except Exception as e:
                    logger.error(f"Description fetch error: {e}")
        
        if should_stop() and not products_with_descriptions:
            _progress.current_phase = "Stopped by user"
            _progress.is_running = False
            return _progress
        
        logger.info(f"Phase 2 complete: Fetched {len(products_with_descriptions)} descriptions")
        
        # Phase 3: Save to database
        _progress.current_phase = "Saving to database"
        update_progress()
        
        for product in products_with_descriptions:
            if should_stop():
                break
            if db.add_product(
                sku=product['sku'],
                name=product['name'],
                product_url=product.get('url'),
                image_url=product.get('img_url'),
                description=product.get('description')
            ):
                _progress.products_added += 1
                _progress.newly_added_skus.append(product['sku'])
        
        logger.info(f"Phase 3 complete: Added {_progress.products_added} products")
        
        _progress.current_phase = "Stopped by user" if should_stop() else "Complete"
        _progress.is_running = False
        update_progress()
        
        return _progress
        
    except Exception as e:
        logger.exception("Discovery failed")
        _progress.error = str(e)
        _progress.is_running = False
        _progress.current_phase = "Failed"
        update_progress()
        return _progress


def run_discovery_from_config(
    progress_callback: Optional[Callable[[DiscoveryProgress], None]] = None
) -> DiscoveryProgress:
    """Run discovery using settings from config file."""
    from ..core.config import get_config
    
    config = get_config()
    
    user_agents = config.get_list('scraper', 'user_agents')
    
    return run_discovery(
        base_url=config.get('scraper', 'base_url'),
        start_page=config.get_int('scraper', 'start_page', default=1),
        end_page=config.get_int('scraper', 'end_page', default=100),
        user_agents=user_agents,
        timeout=config.get_int('scraper', 'timeout', default=30),
        listing_workers=config.get_int('workers', 'discovery_listing', default=4),
        description_workers=config.get_int('workers', 'discovery_description', default=8),
        progress_callback=progress_callback
    )
