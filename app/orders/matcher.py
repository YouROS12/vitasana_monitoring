"""
Product Matching Logic.
Matches WooCommerce order items to Vitasana monitored products.
Strategy:
1. Strict SKU Match (High Confidence)
2. Double-Check: Verify Name Similarity on SKU match
3. Fallback: Fuzzy Name Match if SKU fails (Medium Confidence)
"""

import logging
from typing import Dict, Optional, List, Any, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class ProductMatcher:
    """Logic to match external items to local products."""
    
    def __init__(self, db_products: List[Dict[str, Any]]):
        """
        Initialize with list of local products.
        Expects products to have 'sku' and 'name' fields.
        """
        self.products = db_products
        self.sku_map = {str(p['sku']): p for p in db_products}
        self.name_map = {p['name'].lower(): p for p in db_products}
        
    def _calculate_similarity(self, a: str, b: str) -> float:
        """Return similarity float 0.0-1.0."""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
    
    def match_item(self, item_sku: str, item_name: str) -> Tuple[Optional[Dict[str, Any]], str, float]:
        """
        Match an item to a local product.
        
        Returns:
            Tuple(Matched Product Dict, Match Method, Confidence Score)
            Match Method: 'sku_verified', 'sku_only', 'name_exact', 'name_fuzzy', None
        """
        item_sku_str = str(item_sku).strip()
        item_name_clean = item_name.strip()
        
        # 1. Try SKU Match
        if item_sku_str and item_sku_str in self.sku_map:
            product = self.sku_map[item_sku_str]
            
            # Double Check: Verify Name Similarity
            sim = self._calculate_similarity(item_name_clean, product['name'])
            
            if sim > 0.4:  # Allowing some variation, but must be somewhat similar
                logger.debug(f"Match Verified: SKU {item_sku_str} verified by name sim {sim:.2f}")
                return product, 'sku_verified', 1.0
            else:
                logger.warning(f"SKU Match Warning: SKU {item_sku_str} matches but names differ significantly ({sim:.2f})")
                # Still return match but mark as warning? For now treating as valid match but lower confidence
                return product, 'sku_only', 0.9

        # 2. Try Exact Name Match
        if item_name_clean.lower() in self.name_map:
            return self.name_map[item_name_clean.lower()], 'name_exact', 0.95
        
        # 3. Try Fuzzy Name Match
        best_match = None
        best_score = 0.0
        
        # Optimization: Filter roughly by length first to reduce comparisons? 
        # For < 5000 products, linear scan is acceptable (approx 10-20ms)
        for product in self.products:
            score = self._calculate_similarity(item_name_clean, product['name'])
            if score > best_score:
                best_score = score
                best_match = product
        
        if best_score >= 0.85:  # High threshold for auto-matching
            logger.info(f"Fuzzy Match: '{item_name_clean}' ~= '{best_match['name']}' ({best_score:.2f})")
            return best_match, 'name_fuzzy', best_score
            
        return None, 'none', 0.0
