
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ProductData:
    """Standardized product structure for all providers."""
    sku: str
    name: str
    price: float
    stock_status: str  # 'instock', 'outofstock', 'onbackorder'
    stock_quantity: int
    url: str
    image_url: Optional[str] = None
    supplier_sku: Optional[str] = None
    last_updated: datetime = datetime.now()
    
    # Extra data for specific logic (e.g. buying price for margin calc)
    buying_price: Optional[float] = None
    currency: str = "MAD"

class DataSourceProvider(ABC):
    """
    Interface for any Supplier/Competitor Data Source.
    Implement this class to create a new 'Plugin' (e.g. for AliExpress, Jumia, Distributors).
    """
    
    @abstractmethod
    def authenticate(self) -> bool:
        """Perform login or API auth."""
        pass

    @abstractmethod
    def search_products(self, query: str) -> List[ProductData]:
        """Search products on the source."""
        pass

    @abstractmethod
    def get_product_details(self, sku: str) -> Optional[ProductData]:
        """Get fresh details for a specific product."""
        pass
        
    @abstractmethod
    def get_all_products(self) -> List[ProductData]:
        """
        Optional: Get catalog export if supported.
        If not supported, raise NotImplementedError or return empty.
        """
        pass
