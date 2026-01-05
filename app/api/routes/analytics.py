"""
Analytics API Routes.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any
import pandas as pd
from datetime import datetime, timedelta

from ...core.database import get_database

router = APIRouter()

@router.get("/pulse")
async def get_market_pulse(hours: int = 24):
    """
    Get market pulse analytics:
    - Fastest Movers (Stock drops)
    - Low Stock Items
    """
    db = get_database()
    
    # Fetch raw history for calculations
    # optimization: perform grouping in SQL? 
    # For now, pandas is flexible.
    
    raw_history = db.get_full_history(hours=hours)
    
    if not raw_history:
        return {
            "fastest_movers": [],
            "low_stock": [],
            "stats": {"total_monitored": 0}
        }
        
    df = pd.DataFrame(raw_history)
    
    # Ensure timestamp is datetime
    # Use 'mixed' or handle ISO format explicitly
    try:
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601', utc=True)
    except Exception:
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce', utc=True)
    
    # 1. Fastest Movers (Sales Velocity)
    # Group by SKU
    movers = []
    for sku, group in df.groupby('product_sku'):
        group = group.sort_values('timestamp')
        if len(group) < 2:
            continue
            
        start_stock = group.iloc[0]['stock']
        end_stock = group.iloc[-1]['stock']
        name = group.iloc[0]['name']
        
        # We look for DROPS in stock (sales)
        # Verify valid data (not None)
        if pd.isna(start_stock) or pd.isna(end_stock):
            continue
            
        diff = start_stock - end_stock
        
        # Filter out massive drops that might be resets (e.g. > 1000?) 
        # or negative drops (restock)
        if diff > 0:
            movers.append({
                "sku": sku,
                "name": name,
                "sales_est": int(diff),
                "start_stock": int(start_stock),
                "end_stock": int(end_stock),
                "velocity": round(diff / hours * 24, 1) # projected daily
            })
            
    # Sort by sales estimate
    movers.sort(key=lambda x: x['sales_est'], reverse=True)
    
    # 2. Low Stock (Latest status)
    # We can just fetch latest statuses from DB simpler
    latest = db.get_latest_statuses()
    low_stock = [
        p for p in latest 
        if p.get('stock') is not None 
        and isinstance(p['stock'], int) 
        and 0 < p['stock'] < 10
    ]
    low_stock.sort(key=lambda x: x['stock'])
    
    return {
        "fastest_movers": movers[:50],
        "low_stock": low_stock[:50],
        "stats": {
            "total_monitored": len(latest),
            "movers_count": len(movers)
        }
    }
@router.get("/opportunities")
async def get_opportunities(days: int = 7, min_price: float = 0, min_margin: float = 0):
    """
    Get 'Gold Mine' opportunities: High Velocity + High Margin VALUE + Trend.
    
    Algorithm (v3):
    1. Calculate Sales Velocity for CURRENT period (last N days)
    2. Calculate Sales Velocity for PREVIOUS period (N to 2N days ago)
    3. Calculate Margin MAD = Selling Price - Buying Price
    4. Daily Profit = Velocity × Margin MAD
    5. Trend = Compare current vs previous velocity
    """
    db = get_database()
    
    # Helper function to calculate velocity from history
    def calc_velocity_map(history_records, num_days):
        if not history_records:
            return {}
        df = pd.DataFrame(history_records)
        try:
            df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601', utc=True)
        except:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce', utc=True)
        df = df.sort_values(['product_sku', 'timestamp'])
        
        velocity_map = {}
        for sku, group in df.groupby('product_sku'):
            if len(group) < 2:
                continue
            group = group.sort_values('timestamp')
            group['prev_stock'] = group['stock'].shift(1)
            group['diff'] = group['prev_stock'] - group['stock']
            sales = group[group['diff'] > 0]['diff'].sum()
            daily_v = sales / num_days
            if daily_v > 0:
                velocity_map[sku] = daily_v
        return velocity_map
    
    # Get CURRENT period velocity (last N days)
    current_history = db.get_stock_history_lite(hours=days*24)
    velocity_current = calc_velocity_map(current_history, days)
    
    # Get PREVIOUS period velocity (N to 2N days ago)
    # We fetch 2N days, then filter to only the older half
    full_history = db.get_stock_history_lite(hours=days*24*2)
    if full_history:
        df_full = pd.DataFrame(full_history)
        try:
            df_full['timestamp'] = pd.to_datetime(df_full['timestamp'], format='ISO8601', utc=True)
        except:
            df_full['timestamp'] = pd.to_datetime(df_full['timestamp'], errors='coerce', utc=True)
        
        cutoff = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=days)
        prev_records = df_full[df_full['timestamp'] < cutoff].to_dict('records')
        velocity_prev = calc_velocity_map(prev_records, days) if prev_records else {}
    else:
        velocity_prev = {}
    
    if not velocity_current:
        return {"opportunities": [], "count": 0}
    
    # Get Latest Product Info
    latest = db.get_latest_statuses()
    
    # Calculate & Rank Opportunities
    results = []
    
    for item in latest:
        sku = item['sku']
        velocity = velocity_current.get(sku, 0.0)
        prev_velocity = velocity_prev.get(sku, 0.0)
        
        if velocity <= 0.1:
            continue
        
        selling_price = float(item.get('price') or 0)
        buying_price = float(item.get('final_price') or 0)
        discount_pct = float(item.get('discount_percent') or 0)
        stock = int(item.get('stock') or 0)
        
        if selling_price <= 0 or buying_price <= 0:
            continue
        
        margin_mad = selling_price - buying_price
        
        if selling_price < min_price:
            continue
        if margin_mad < min_margin:
            continue
        
        daily_profit = velocity * margin_mad
        
        # Calculate Trend
        if prev_velocity > 0:
            change_pct = ((velocity - prev_velocity) / prev_velocity) * 100
            if change_pct > 10:
                trend = "↑"
            elif change_pct < -10:
                trend = "↓"
            else:
                trend = "→"
        else:
            # New product or no previous data
            trend = "🆕"
            change_pct = 0
        
        if daily_profit >= 1.0:
            results.append({
                "sku": sku,
                "name": item['name'],
                "selling_price": round(selling_price, 2),
                "buying_price": round(buying_price, 2),
                "margin_mad": round(margin_mad, 2),
                "discount_pct": round(discount_pct, 1),
                "velocity": round(velocity, 2),
                "trend": trend,
                "trend_pct": round(change_pct, 1),
                "daily_profit": round(daily_profit, 2),
                "stock": stock
            })
    
    results.sort(key=lambda x: x['daily_profit'], reverse=True)
    
    return {
        "count": len(results),
        "days_analyzed": days,
        "filters": {"min_price": min_price, "min_margin": min_margin},
        "opportunities": results[:100]
    }
