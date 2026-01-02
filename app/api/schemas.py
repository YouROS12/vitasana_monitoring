"""
Pydantic schemas for API request/response validation.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ==================== Product Schemas ====================

class ProductBase(BaseModel):
    """Base product fields."""
    sku: int
    name: str
    product_url: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None


class ProductWithStatus(ProductBase):
    """Product with latest monitoring status."""
    discovered_at: Optional[str] = None
    last_checked_at: Optional[str] = None
    stock: Optional[int] = None
    price: Optional[float] = None
    discount_percent: Optional[float] = None
    final_price: Optional[float] = None
    availability: Optional[str] = None
    points: Optional[int] = None
    last_monitored: Optional[str] = None


class ProductListResponse(BaseModel):
    """Response for product list."""
    total: int
    products: List[ProductWithStatus]


class MonitoringRecord(BaseModel):
    """Single monitoring history record."""
    id: int
    product_sku: int
    timestamp: str
    stock: Optional[int] = None
    price: Optional[float] = None
    discount_percent: Optional[float] = None
    final_price: Optional[float] = None
    availability: Optional[str] = None
    points: Optional[int] = None


class ProductHistoryResponse(BaseModel):
    """Response for product history."""
    sku: int
    name: str
    history: List[MonitoringRecord]


# ==================== Task Schemas ====================

class DiscoveryRequest(BaseModel):
    """Request to run product discovery."""
    start_page: int = Field(default=1, ge=1)
    end_page: int = Field(default=100, ge=1)
    listing_workers: int = Field(default=4, ge=1, le=20)
    description_workers: int = Field(default=8, ge=1, le=20)


class DiscoveryProgress(BaseModel):
    """Discovery task progress."""
    total_pages: int
    pages_scanned: int
    products_found: int
    products_added: int
    is_running: bool
    current_phase: str
    error: Optional[str] = None


class MonitoringRequest(BaseModel):
    """Request to run product monitoring."""
    limit: Optional[int] = Field(default=None, ge=1)
    offset: int = Field(default=0, ge=0)
    keywords: Optional[str] = None  # Comma-separated
    workers: int = Field(default=5, ge=1, le=20)


class MonitoringProgress(BaseModel):
    """Monitoring task progress."""
    total_products: int
    products_processed: int
    products_updated: int
    products_failed: int
    is_running: bool
    current_phase: str
    error: Optional[str] = None


# ==================== Generic Schemas ====================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    database_products: int
    database_records: int


class TaskResponse(BaseModel):
    """Generic task response."""
    success: bool
    message: str
    task_id: Optional[str] = None
