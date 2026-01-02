"""
Mass Market Scanner.
Recursively scans the LACDP catalog using prefix search to map all products
efficiently while minimizing requests.
"""

import logging
import time
import string
import threading
from typing import List, Set, Deque
from collections import deque
from datetime import datetime
import requests

from ..core.database import get_database
from ..auth.session import create_auth_session_from_config

logger = logging.getLogger(__name__)

SEARCH_URL = "https://webdash.lacdp.ma/client_dash/filter_product"
MAX_RESULTS = 40  # Server-side limit

class MassScanner:
    def __init__(self):
        self.db = get_database()
        self.session_manager = create_auth_session_from_config()
        self.session = self._init_session()
        self.stop_event = threading.Event()
        
        # Alphabet for recursion: a-z, 0-9, space
        self.alphabet = list(string.ascii_lowercase + string.digits + ' ')
        
    def _init_session(self):
        """Initialize authenticated session."""
        sess_config = self.session_manager.get_session_config()
        if not sess_config:
            raise ValueError("Could not authenticate")
            
        session = requests.Session()
        for k, v in sess_config.cookies.items():
            session.cookies.set(k, v, domain="lacdp.ma")
            
        session.headers.update({
            "User-Agent": sess_config.headers.get("User-Agent", "Vitasana/1.0"),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://webdash.lacdp.ma/"
        })
        return session

    def scan(self, optimized: bool = False, progress_callback=None):
        """
        Start the recursive scan.
        Args:
            optimized: If True, load prefixes from data/optimized_prefixes.json
            progress_callback: Optional callback(current_phase, processed_count, total_count)
        """
        logger.info(f"Starting Mass Market Scan (Optimized={optimized})...")
        
        queue: Deque[str] = deque()
        
        if optimized:
            import json
            from pathlib import Path
            try:
                with open("data/optimized_prefixes.json", "r", encoding="utf-8") as f:
                    prefixes = json.load(f)
                    queue.extend(prefixes)
                logger.info(f"Loaded {len(queue)} optimized prefixes.")
            except FileNotFoundError:
                if progress_callback:
                    progress_callback("Error: optimized_prefixes.json missing", 0, 0)
                logger.error("Optimized prefixes not found. Run 'cli.py optimize' first.")
                return
        else:
            queue.extend(self.alphabet)
            
        visited: Set[str] = set()
        
        total_products = 0
        total_prefixes = len(queue)
        prefixes_processed = 0
        start_time = time.time()
        
        try:
            while queue and not self.stop_event.is_set():
                prefix = queue.popleft()
                prefixes_processed += 1
                
                if prefix in visited or len(prefix) > 5: # Safety depth limit
                    continue
                    
                visited.add(prefix)
                
                # Update progress
                if progress_callback:
                    progress_callback(f"Scanning '{prefix}'", total_products, prefixes_processed, total_prefixes)
                
                try:
                    count = self._process_prefix(prefix)
                    total_products += count
                    
                    # Store effective prefix
                    if count > 0:
                        self.db.record_scan_prefix(prefix, count)
                    
                    # Drill down if capped (ONLY in non-optimized mode or if needed)
                    # In optimized mode, we shouldn't drill down usually, but if we do:
                    if count >= MAX_RESULTS and not optimized:
                        logger.info(f"Prefix '{prefix}' hit limit ({count}). Expanding...")
                        for char in self.alphabet:
                            new_prefix = prefix + char
                            queue.append(new_prefix)
                            
                    time.sleep(0.2) # Rate limiting
                    
                except Exception as e:
                    logger.error(f"Error scanning '{prefix}': {e}")
                    time.sleep(1) # Backoff
                    
        except KeyboardInterrupt:
            logger.info("Scan interrupted by user.")
            
        duration = time.time() - start_time
        logger.info(f"Scan complete. Processed {len(visited)} prefixes. Upserted {total_products} products in {duration:.2f}s.")
        
        if progress_callback:
            progress_callback("Complete", total_products, prefixes_processed, total_prefixes)

    def _process_prefix(self, prefix: str) -> int:
        """Fetch and persist products for a prefix."""
        logger.debug(f"Scanning: {prefix}")
        
        response = self.session.get(
            SEARCH_URL,
            params={"title": prefix},
            timeout=10
        )
        
        if response.status_code != 200:
            logger.warning(f"Failed to fetch '{prefix}': {response.status_code}")
            return 0
            
        try:
            data = response.json()
        except Exception:
            # Empty response or invalid JSON usually means no results
            return 0
            
        if not isinstance(data, list):
            return 0
            
        # Persist products
        new_count = 0
        for item in data:
            if self.db.upsert_product_from_search(item):
                new_count += 1
                
        logger.info(f"Prefix '{prefix}': {len(data)} items")
        return len(data)

    def stop(self):
        """Stop the scanner."""
        self.stop_event.set()
