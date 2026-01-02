"""
Health check endpoint.
"""

from fastapi import APIRouter

from ..schemas import HealthResponse
from ...core.database import get_database

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Check API health and database status."""
    db = get_database()
    
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        database_products=db.get_product_count(),
        database_records=0  # TODO: Add record count
    )
