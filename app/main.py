"""
FastAPI application for Vitasana Monitoring.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.core.config import get_config
from app.core.logging import setup_logging
from app.core.database import get_database
from app.api.routes import health, products, discovery, monitoring, orders, analytics

# Initialize logging
config = get_config()
setup_logging(
    log_file=config.log_path,
    level=config.get('general', 'log_level', default='INFO')
)

# Initialize database
get_database()

# Create FastAPI app
app = FastAPI(
    title="Vitasana Monitoring API",
    description="API for pharmaceutical product monitoring and discovery",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware (allow Streamlit to access)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(discovery.router, prefix="/api")
app.include_router(monitoring.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Vitasana Monitoring API",
        "version": "1.0.0",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
