
"""
Analysis Engine.
Handles heavy data processing for Gold Mine and Market Pulse in the background.
"""

import logging
import json
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any

from app.core.database import get_database

logger = logging.getLogger(__name__)

class GoldMineAnalyzer:
    def __init__(self, output_dir: str = "data/analytics"):
        self.db = get_database()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def run_full_analysis(self) -> Dict[str, Any]:
        """Run analysis for multiple timeframes and save results."""
        logger.info("Starting Daily Gold Mine Analysis...")
        
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "periods": {}
        }
        
        # Analyze standard periods
        for days in [3, 7, 14, 30]:
            logger.info(f"Analyzing last {days} days...")
            data = self._analyze_period(days)
            results["periods"][str(days)] = data
            
        # Save to file
        output_file = self.output_dir / "gold_mine_latest.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Analysis complete. Saved to {output_file}")
        return results

    def _analyze_period(self, days: int) -> List[Dict[str, Any]]:
        """Calculate opportunities for a specific day range."""
        
        # Helper: Velocity Map
        def calc_velocity_map(history_records, num_days):
            if not history_records:
                return {}
            df = pd.DataFrame(history_records)
            # Safe timestamp conversion
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
            
            df = df.sort_values(['product_sku', 'timestamp'])
            
            velocity_map = {}
            for sku, group in df.groupby('product_sku'):
                if len(group) < 2:
                    continue
                group = group.sort_values('timestamp')
                group['prev_stock'] = group['stock'].shift(1)
                group['diff'] = group['prev_stock'] - group['stock']
                # Only count positive sales (stock drops)
                sales = group[group['diff'] > 0]['diff'].sum()
                daily_v = sales / num_days
                if daily_v > 0:
                    velocity_map[sku] = daily_v
            return velocity_map

        # 1. Fetch Data
        # Current period
        current_history = self.db.get_stock_history_lite(hours=days*24)
        velocity_current = calc_velocity_map(current_history, days)
        
        # Previous period (for trend)
        full_history = self.db.get_stock_history_lite(hours=days*24*2)
        velocity_prev = {}
        
        if full_history:
            df_full = pd.DataFrame(full_history)
            df_full['timestamp'] = pd.to_datetime(df_full['timestamp'], utc=True, errors='coerce')
            cutoff = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=days)
            
            # Filter for previous N days
            prev_records = df_full[df_full['timestamp'] < cutoff].to_dict('records')
            velocity_prev = calc_velocity_map(prev_records, days)
        
        if not velocity_current:
            return []

        # 2. Latest Prices/Stock
        latest = self.db.get_latest_statuses()
        
        # 3. Compile Results
        results = []
        for item in latest:
            sku = item['sku']
            velocity = velocity_current.get(sku, 0.0)
            prev_velocity = velocity_prev.get(sku, 0.0)
            
            if velocity <= 0:
                continue
                
            selling_price = float(item.get('price') or 0)
            buying_price = float(item.get('final_price') or 0)
            stock = int(item.get('stock') or 0)
            margin_mad = selling_price - buying_price
            daily_profit = velocity * margin_mad
            
            # Trend
            trend = "🆕"
            change_pct = 0
            if prev_velocity > 0:
                change_pct = ((velocity - prev_velocity) / prev_velocity) * 100
                if change_pct > 10: trend = "↑"
                elif change_pct < -10: trend = "↓"
                else: trend = "→"
            
            results.append({
                "sku": sku,
                "name": item['name'],
                "selling_price": round(selling_price, 2),
                "buying_price": round(buying_price, 2),
                "margin_mad": round(margin_mad, 2),
                "velocity": round(velocity, 2),
                "trend": trend,
                "trend_pct": round(change_pct, 1),
                "daily_profit": round(daily_profit, 2),
                "stock": stock
            })
            
        # Sort by Velocity (Top Selling)
        results.sort(key=lambda x: x['velocity'], reverse=True)
        return results[:200]  # Top 200 is enough for UI
