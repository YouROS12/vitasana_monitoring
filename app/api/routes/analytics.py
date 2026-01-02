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
async def get_opportunities(days: int = 7):
    """
    Get 'Gold Mine' opportunities: High Velocity + High Discount.
    Algorithm:
    1. Calculate Sales Velocity (Units/Day) from last N days history (ignoring restocks).
    2. Get current Discount % from latest status.
    3. Score = Velocity * Discount.
    """
    db = get_database()
    
    # 1. Calculate Velocity
    history_records = db.get_full_history(hours=days*24)
    if not history_records:
        return {"opportunities": [], "count": 0}
        
    df = pd.DataFrame(history_records)
    
    # robust timestamp
    try:
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601', utc=True)
    except:
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce', utc=True)
        
    df = df.sort_values(['product_sku', 'timestamp'])
    
    # Group by SKU and calculate differences
    # We want sum of (prev - curr) where prev > curr
    
    velocity_map = {}
    
    for sku, group in df.groupby('product_sku'):
        if len(group) < 2:
            continue
            
        group = group.sort_values('timestamp')
        
        # Calculate diffs: shift(1) is previous row
        # stock_diff = prev - curr
        group['prev_stock'] = group['stock'].shift(1)
        group['diff'] = group['prev_stock'] - group['stock']
        
        # Sales are positive diffs. Restocks are negative diffs.
        sales = group[group['diff'] > 0]['diff'].sum()
        
        # Daily velocity
        daily_v = sales / days
        if daily_v > 0:
            velocity_map[sku] = daily_v
    
    # 2. Get Margin Info
    latest = db.get_latest_statuses()
    
    # 3. Rank Opportunities
    results = []
    
    for item in latest:
        sku = item['sku'] # database.py returns 'sku' column
        velocity = velocity_map.get(sku, 0.0)
        
        if velocity <= 0.1: # Eliminate things selling less than 1 every 10 days
            continue
            
        discount = float(item.get('discount_percent') or 0)
        final_price = float(item.get('final_price') or 0)
        stock = int(item.get('stock') or 0)
        
        # Score Logic
        score = velocity * discount
        
        # Only meaningful opportunities
        if score > 0.5: 
            results.append({
                "sku": sku,
                "name": item['name'],
                "velocity": round(velocity, 2), # units/day
                "discount_percent": round(discount, 1),
                "price": final_price,
                "stock": stock,
                "score": round(score, 1)
            })
            
    # Sort DESC by Score
    results.sort(key=lambda x: x['score'], reverse=True)
    
    return {
        "count": len(results),
        "days_analyzed": days,
        "opportunities": results[:100] # Top 100
    }
