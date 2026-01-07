"""
AI Product Matcher Prototype (Cost-Optimized).
Uses text analysis to compare two products and return a confidence score.
Only flags "unsure" items for human review.
"""

import json
import os
from typing import Dict, Any, Optional

# Placeholder for typing
try:
    from openai import OpenAI
except ImportError:
    OpenAI = Any

class AISmartMatcher:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = None
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)

    def verify_match(self, supplier_product: Dict[str, Any], store_product: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ask AI if these two products are a match (Text Only).
        
        Args:
            supplier_product: {name, price, description}
            store_product: {name, sku, price}
            
        Returns:
            {
                "match": bool,      # True/False (Yes/No)
                "confidence": int,  # 0-100 Similarity Score
                "reason": str,      # Explanation
                "flag": str         # "manual_review" if not sure
            }
        """
        if not self.client:
            return {"error": "No API Key configured"}

        prompt = f"""
        Compare these two products and determine if they are the SAME ITEM.
        
        PRODUCT A (Supplier):
        Name: {supplier_product.get('name')}
        Price: {supplier_product.get('price')} (Checks for huge price discrepancies indicating Pack vs Single)
        Desc: {supplier_product.get('description', 'N/A')[:200]}...
        
        PRODUCT B (Store):
        Name: {store_product.get('name')}
        Price: {store_product.get('price')}
        
        TASK:
        1. Analyze semantic similarity (e.g. "Vaccuum 500W" == "SuperClean 500W").
        2. Detect "Pack" conflicts (e.g. 1pc vs 2pcs).
        3. Output a Confidence Score (0-100).
        
        RETURN JSON:
        {{
            "match": true/false,
            "confidence": 85,
            "reason": "Names differ but specs match exactly.",
            "flag": "none" (or "manual_review" if confidence < 80)
        }}
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini", # Cheap and fast
                messages=[
                    {"role": "system", "content": "You are a precise comparison engine. Output valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0
            )
            
            content = response.choices[0].message.content
            content = content.replace("```json", "").replace("```", "").strip()
            return json.loads(content)
            
        except Exception as e:
            return {"match": False, "confidence": 0, "reason": str(e), "flag": "error"}

if __name__ == "__main__":
    matcher = AISmartMatcher("sk-DUMMY")
    # Test
    res = matcher.verify_match(
        {"name": "Generic Wireless Mouse", "price": 5},
        {"name": "ProGamer Mouse 2.4Ghz", "price": 15}
    )
    print(res)
