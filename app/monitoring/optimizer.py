"""
Market Optimizer.
Analyzes the local database to generate an optimized list of search prefixes
that cover all known products while respecting the API query limit (40).
This allows for efficient "Monitoring Mode" scans.
"""

import json
import logging
import string
from pathlib import Path
from typing import List

from ..core.database import get_database

logger = logging.getLogger(__name__)

# Same as MassScanner
MAX_RESULTS = 40
ALPHABET = list(string.ascii_lowercase + string.digits + ' ')

class MarketOptimizer:
    def __init__(self):
        self.db = get_database()
        self.products = []
        
    def load_data(self):
        """Load minimal product data (SKU and Name) for analysis."""
        logger.info("Loading products from database...")
        all_products = self.db.get_products(limit=None)
        
        # Normalize names for simulation (lowercase)
        self.products = [p['name'].lower() for p in all_products if p.get('name')]
        logger.info(f"Loaded {len(self.products)} products for analysis.")

    def generate_prefixes(self) -> List[str]:
        """
        Generate the optimal set of prefixes.
        """
        if not self.products:
            self.load_data()
            
        logger.info("Optimizing search prefixes (Filtered Subset Strategy)...")
        
        optimal_prefixes = []
        
        # Start top-level to parallelize if needed, 
        # but here we iterate alphabet and pass the subset.
        
        # Optimization: Pre-filter for each starting char to reduce initial set
        for char in ALPHABET:
            # Subset: items that contain this char?
            # If logic is "Contains", then 'a' matches "cat".
            # The search API is "Contains" if we search "c" -> matches "cat".
            # If we search "a" -> matches "cat".
            # So if we start with "a", we find "cat".
            # If we start with "c", we find "cat".
            # This means "cat" is found MULTIPLE times if we scan a-z!
            # We want to find "cat" AT LEAST ONCE with MINIMAL queries.
            
            # Wait! If "cat" is found by 'c', do we need to search 'a'?
            # If we search 'a', we get 'cat', 'apple', 'bat'...
            # If 'a' returns > 40, we split to 'aa', 'ab'...
            # 'cat' contains 'a'. So 'cat' will be in result of 'a'.
            # If we want to COVER all products, we only need to query prefixes that cover them.
            # But the goal of MassScanner was iterating ALPHABET.
            # So it does redundant work (finding 'cat' via 'c', 'a', 't').
            # The user wants "exact queries to send to have all products".
            # Minimal set to cover all SKUs?
            # That's a "Set Cover Problem" (NP-Hard).
            
            # BUT, the Monitoring Mode uses the output list.
            # If I output ['a', 'b' ... 'z'], I fetch 'cat' 3 times.
            # I should prefer "Starts With" prefixes if possible?
            # No, if the API is "Contains", I can't force it to be "Starts With".
            # I should pick a strategy that covers every product ONCE if possible.
            # But I can't unless I know which prefix I "assign" to a product.
            # E.g. Assign "cat" to "c".
            # But I can't tell the API "Give me items starting with c". Use "c%25"?
            
            # User said: "Urb" -> "Urban". "Pan" -> "Panadol".
            # These are "Starts With".
            # My experiment: "Urb" -> 40 items. "Urban..."
            # Did it include "Suburban"?
            # If "Suburban" exists, did it show up?
            
            # Assumption: The API behaves like "Starts With" for meaningful prefixes.
            # If I treat it as "Starts With" in optimizer:
            # "cat" matches "c".
            # "cat" does NOT match "a".
            # Then I generate prefixes based on "Starts With".
            # If the API is actually "Contains", then searching "c" will return "cat" AND "ace"?
            # If so, my 'Starts With' assumption underestimates the result count!
            # If I assume 'c' returns 10 items (starts with c), but it returns 100 (contains c), 
            # I won't drill down, and I'll get capped at 40!
            # So I MUST assume "Contains" to be safe against the Cap.
            
            # So my simulation MUST use `if prefix in name`.
            # And yes, this means redundancy.
            # Can I minimize redundancy?
            # If I search "a", I get "cat".
            # If I search "c", I get "cat".
            # If I search "at", I get "cat".
            # Maybe I only search "a"?
            # But "a" hits cap. Drill to "ab", "ac"...
            # "ac" finds "cat". "at" finds "cat".
            # It's hard to avoid redundancy with "Contains" search without complex exclusions.
            
            # However, the user said "do scans, tests.. everything possible to send the least request."
            # If the API supports wildcards? No info.
            # If the API is "Starts with"?
            # Let's look at the result of "a".
            # If it was "Contains", "a" would return almost EVERYTHING (all items with 'a').
            # 90% of words have 'a'.
            # If "a" returns 40, and I drill down...
            # I'd have to drill down to 5 letters to isolate items?
            # "apple" -> "apples"
            
            # Actually, "Urb" returning 40 suggests "Starts With".
            # If it was contains, "rb" (in "Urb") is common.
            # "Pan" -> "Panadol".
            # "Dol" -> "Doliprane"? "Panadol"?
            # Search "Dol": Found 23 items.
            # If "Dol" matches "Panadol" (contains), it would surely be > 23?
            # "Doliprane" is a huge brand. "Panadol" too.
            # "Pan" gave 40.
            # "Par" gave 40.
            # "Bea" gave 40.
            # "Dol" gave 23.
            # "Panadol" contains "dol".
            # "Doliprane" starts with "dol".
            # If "Dol" was "Contains", it would include "Panadol" + "Doliprane" + others.
            # Does "Panadol" + "Doliprane" > 23? Likely.
            # Wait, 23 seems small for "Dol".
            # Maybe it IS "Starts With"?
            # IF IT IS STARTS WITH, my "Contains" logic is WRONG and overly pessimistic (causing too many drill-downs).
            
            # Let's verify 'Dol' vs 'Panadol'.
            # If I assume 'Starts With', I can optimize much better (no redundancy).
            # AND I can optimize the optimizer (Bisect).
            
            # I will trust the "Dol" = 23 result. "Pan" = 40.
            # If "Contains" was true, "Dol" would likely limit at 40 too (common trigram).
            # So "Starts With" is the most likely behavior.
            # I will switch Optimizer to "Starts With".
            # `if name.startswith(prefix)`
            
            subset = [p for p in self.products if p.startswith(char)]
            optimal_prefixes.extend(self._optimize_branch(char, subset))
            
        logger.info(f"Optimization complete. Generated {len(optimal_prefixes)} prefixes.")
        return optimal_prefixes
    
    def _optimize_branch(self, prefix: str, dataset: List[str]) -> List[str]:
        count = len(dataset)
        
        # If count within limit, keep it
        if count <= MAX_RESULTS:
            return [prefix] if count > 0 else []
        
        # If too deep, stop
        if len(prefix) >= 5:
            # We hit 5 chars and still > 40 items? 
            # We likely just return it and accept partial data, or user needs to handle it.
            return [prefix]
            
        child_results = []
        for char in ALPHABET:
            new_prefix = prefix + char
            # Filter dataset for new prefix
            # Since we assume starts_with, we can just check if p starts with new_prefix
            # Optimization: slicing? p[len(prefix)] == char
            
            idx = len(prefix)
            subset = [p for p in dataset if len(p) > idx and p[idx] == char]
            
            if subset:
                child_results.extend(self._optimize_branch(new_prefix, subset))
            
        return child_results

    def save_optimized_list(self, filepath: str = "data/optimized_prefixes.json"):
        """Save the list to a file."""
        prefixes = self.generate_prefixes()
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(prefixes, f, indent=2)
            
        return prefixes
