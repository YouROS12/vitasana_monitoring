"""
Product API endpoints.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List

from ..schemas import ProductListResponse, ProductWithStatus, ProductHistoryResponse, MonitoringRecord
from ...core.database import get_database

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ProductListResponse)
async def list_products(
    limit: Optional[int] = Query(None, ge=1, le=100000),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Search by name or SKU")
):
    """
    List all products with optional filtering.
    """
    db = get_database()
    
    keywords = [k.strip() for k in search.split(',')] if search else None
    products = db.get_products(limit=limit, offset=offset, keywords=keywords)
    
    return ProductListResponse(
        total=len(products),
        products=[ProductWithStatus(**p) for p in products]
    )


@router.get("/latest", response_model=List[ProductWithStatus])
async def get_latest_statuses(
    limit: Optional[int] = Query(100, ge=1, le=100000),
    search: Optional[str] = Query(None, description="Search by name or SKU")
):
    """
    Get latest monitoring status for all products.
    """
    db = get_database()
    statuses = db.get_latest_statuses()
    
    # Apply search filter
    if search:
        search_lower = search.lower()
        statuses = [
            s for s in statuses 
            if search_lower in s.get('name', '').lower() or search_lower in str(s.get('sku', ''))
        ]
    
    if limit:
        statuses = statuses[:limit]
    
    return [ProductWithStatus(**s) for s in statuses]


@router.get("/{sku}", response_model=ProductWithStatus)
async def get_product(sku: int):
    """
    Get a single product by SKU.
    """
    db = get_database()
    product = db.get_product(sku)
    
    if not product:
        raise HTTPException(status_code=404, detail=f"Product {sku} not found")
    
    # Get latest monitoring record
    last_record = db.get_last_record(sku)
    if last_record:
        product.update({
            'stock': last_record.get('stock'),
            'price': last_record.get('price'),
            'discount_percent': last_record.get('discount_percent'),
            'final_price': last_record.get('final_price'),
            'availability': last_record.get('availability'),
            'points': last_record.get('points'),
            'last_monitored': last_record.get('timestamp')
        })
    
    return ProductWithStatus(**product)


@router.get("/{sku}/history", response_model=ProductHistoryResponse)
async def get_product_history(
    sku: int,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: Optional[int] = Query(100, ge=1, le=1000)
):
    """
    Get monitoring history for a product.
    """
    db = get_database()
    product = db.get_product(sku)
    
    if not product:
        raise HTTPException(status_code=404, detail=f"Product {sku} not found")
    
    history = db.get_product_history(
        sku=sku,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )
    
    return ProductHistoryResponse(
        sku=sku,
        name=product['name'],
        history=[MonitoringRecord(**h) for h in history]
    )
