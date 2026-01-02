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
