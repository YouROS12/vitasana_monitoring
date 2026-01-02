"""
Mass Scanner Experiment.
Tests the feasibility of scraping the entire catalog using search prefixes
instead of sequential product IDs.
"""

import sys
import os
import time
import json
import logging
from typing import List, Dict, Set
from pathlib import Path
import requests

# Add parent directory to path to import app modules
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.auth.session import create_auth_session_from_config
from app.core.config import get_config

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SEARCH_URL = "https://webdash.lacdp.ma/client_dash/filter_product"

class MassScanner:
    def __init__(self):
        self.config = get_config()
        self.session = self._init_session()
        self.found_products: Dict[str, Dict] = {} # sku -> product_data
        
    def _init_session(self):
        """Initialize authenticated session"""
        auth = create_auth_session_from_config()
        sess_config = auth.get_session_config()
        if not sess_config:
            raise ValueError("Could not authenticate")
            
        session = requests.Session()
        # Add cookies
        for cookie_name, cookie_val in sess_config.cookies.items():
            session.cookies.set(cookie_name, cookie_val, domain="lacdp.ma")
            
        # Add headers
        session.headers.update({
            "User-Agent": sess_config.headers.get("User-Agent", "Vitasana/1.0"),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://webdash.lacdp.ma/"
        })
        return session

    def search_prefix(self, prefix: str) -> List[Dict]:
        """Search for a specific prefix"""
        try:
            logger.info(f"Searching prefix: '{prefix}'")
            response = self.session.get(
                SEARCH_URL, 
                params={"title": prefix}, 
                timeout=10
            )
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, list):
                        return data
                    else:
                        logger.warning(f"Unexpected response format for '{prefix}': {type(data)}")
                        return []
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode JSON for '{prefix}'")
                    return []
            else:
                logger.error(f"Error {response.status_code} for '{prefix}'")
                return []
                
        except Exception as e:
            logger.error(f"Exception searching '{prefix}': {e}")
            return []

    def run_experiment(self, prefixes: List[str]):
        """Run the experiment on a list of prefixes"""
        logger.info(f"Starting experiment with {len(prefixes)} prefixes...")
        
        start_time = time.time()
        
        for prefix in prefixes:
            products = self.search_prefix(prefix)
            new_count = 0
            
            for p in products:
                sku = str(p.get('sku') or p.get('id'))
                if sku and sku not in self.found_products:
                    self.found_products[sku] = p
                    new_count += 1
            
            logger.info(f"Prefix '{prefix}': Found {len(products)} products ({new_count} new)")
            time.sleep(0.5) # Polite delay
            
        duration = time.time() - start_time
        logger.info(f"\nExperiment Complete in {duration:.2f}s")
        logger.info(f"Total Unique Products Found: {len(self.found_products)}")
        
        # Save sample results
        os.makedirs("data", exist_ok=True)
        with open("data/mass_scan_results.json", "w", encoding='utf-8') as f:
            json.dump(list(self.found_products.values()), f, indent=2, ensure_ascii=False)
            
        return self.found_products

if __name__ == "__main__":
    # Test shorter prefixes to see if API accepts them
    prefixes_to_test = ["a", "b", "aa", "ab", "7", " "]
    
    scanner = MassScanner()
    scanner.run_experiment(prefixes_to_test)
