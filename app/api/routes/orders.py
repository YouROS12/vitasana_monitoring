"""
Order API endpoints.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from ...orders.service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderItem(BaseModel):
    id: int
    name: str
    sku: Optional[str] = None
    quantity: int
    match_status: str
    matched_sku: Optional[int] = None
    match_score: Optional[float] = None
    stock_status: str
    available_qty: int
    price: Optional[float] = None


class OrderSummary(BaseModel):
    id: int
    number: str
    status: str
    date_created: str
    total_amount: float
    billing: Dict[str, Any]
    items: List[OrderItem]
    fulfillability: str


@router.get("/sync", response_model=List[OrderSummary])
async def sync_orders(status: str = "processing"):
    """
    Sync orders from WooCommerce and check availability.
    """
    service = OrderService()
    try:
        orders = service.sync_orders(status=status, check_stock=True)
        return orders
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=List[OrderSummary])
async def get_order_history(limit: int = 50, status: Optional[str] = None):
    """
    Get stored order history.
    """
    from ...core.database import get_database
    db = get_database()
    try:
        orders = db.get_orders(limit=limit, status=status)
        # Format for response
        result = []
        for o in orders:
            # Reconstruct items list with field mapping (DB -> API)
            items_list = []
            for item in o['items']:
                items_list.append({
                    'id': item['id'],
                    'name': item['product_name'],  # DB: product_name -> API: name
                    'sku': item['sku'],
                    'quantity': item['quantity'],
                    'match_status': item['match_type'], # DB: match_type -> API: match_status
                    'matched_sku': item['matched_sku'],
                    'match_score': None, # DB doesn't store this yet
                    'stock_status': item['stock_status'],
                    'available_qty': item['available_qty'],
                    'price': item['price_at_sync'] # DB: price_at_sync -> API: price
                })

            # Reconstruct OrderSummary structure
            result.append({
                'id': o['id'],
                'number': o['number'],
                'status': o['status'],
                'date_created': o['date_created'],
                'total_amount': o['total_amount'],
                'billing': {
                    'first_name': o.get('first_name'),
                    'last_name': o.get('last_name'),
                    'email': o.get('email')
                },
                'items': items_list,
                'fulfillability': o['fulfillability']
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/customers")
async def get_customers(limit: int = 50):
    """
    Get top customers.
    """
    from ...core.database import get_database
    db = get_database()
    try:
        return db.get_customers(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
