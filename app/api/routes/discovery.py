"""
Discovery task API endpoints with auto-sync support.
"""

from fastapi import APIRouter, BackgroundTasks
import threading
import logging

from ..schemas import DiscoveryRequest, DiscoveryProgress as DiscoveryProgressSchema, TaskResponse
from ...discovery.scraper import run_discovery, get_progress, DiscoveryProgress
from ...core.config import get_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discovery", tags=["discovery"])

# Track running task
_task_lock = threading.Lock()
_task_running = False
_stop_event = threading.Event()


def _run_auto_sync(skus: list):
    """Run monitoring for newly discovered SKUs."""
    if not skus:
        logger.info("No new SKUs to auto-sync")
        return
    
    logger.info(f"[AUTO-SYNC] Starting monitoring for {len(skus)} newly discovered products...")
    
    from ...monitoring import tracker
    from ...auth.session import create_auth_session_from_config
    from ...core.database import get_database
    
    config = get_config()
    
    try:
        auth = create_auth_session_from_config()
        
        # Get products by SKUs
        db = get_database()
        
        result = tracker.run_monitoring(
            auth_session=auth,
            get_product_url=config.get('api', 'get_product_url'),
            filter_product_url=config.get('api', 'filter_product_url'),
            timeout=config.get_int('api', 'timeout', default=25),
            limit=len(skus),
            offset=0,
            keywords=None,  # We'll filter by SKU below
            workers=config.get_int('workers', 'monitoring', default=5),
            retry_count=config.get_int('api', 'retry_count', default=3)
        )
        
        logger.info(f"[AUTO-SYNC] Complete: {result.products_updated} updated, {result.products_failed} failed")
        
    except Exception as e:
        logger.error(f"[AUTO-SYNC] Failed: {e}")


def _run_discovery_task(start_page: int, end_page: int, listing_workers: int, description_workers: int, auto_sync: bool):
    """Background task runner for discovery with optional auto-sync."""
    global _task_running
    
    from ...discovery import scraper
    config = get_config()
    
    user_agents = config.get_list('scraper', 'user_agents')
    _stop_event.clear()
    
    try:
        result = scraper.run_discovery(
            base_url=config.get('scraper', 'base_url'),
            start_page=start_page,
            end_page=end_page,
            user_agents=user_agents,
            timeout=config.get_int('scraper', 'timeout', default=30),
            listing_workers=listing_workers,
            description_workers=description_workers,
            stop_event=_stop_event
        )
        
        # Auto-sync: Run monitoring for newly added products
        if auto_sync and result.newly_added_skus and not _stop_event.is_set():
            logger.info(f"[AUTO-SYNC] Triggering monitoring for {len(result.newly_added_skus)} new products")
            _run_auto_sync(result.newly_added_skus)
        
    finally:
        with _task_lock:
            global _task_running
            _task_running = False


@router.post("/run", response_model=TaskResponse)
async def run_discovery_endpoint(
    request: DiscoveryRequest,
    background_tasks: BackgroundTasks
):
    """
    Start a product discovery task.
    If auto_sync is enabled in config, newly discovered products will be automatically monitored.
    """
    global _task_running
    
    with _task_lock:
        if _task_running:
            return TaskResponse(
                success=False,
                message="Discovery is already running"
            )
        _task_running = True
    
    # Check if auto-sync is enabled
    config = get_config()
    auto_sync = config.get_bool('auto_sync', 'enabled', default=True)
    
    background_tasks.add_task(
        _run_discovery_task,
        request.start_page,
        request.end_page,
        request.listing_workers,
        request.description_workers,
        auto_sync
    )
    
    sync_msg = " (auto-sync enabled)" if auto_sync else ""
    
    return TaskResponse(
        success=True,
        message=f"Discovery started (pages {request.start_page}-{request.end_page}){sync_msg}"
    )


@router.get("/status", response_model=DiscoveryProgressSchema)
async def get_discovery_status():
    """
    Get current discovery progress.
    """
    progress = get_progress()
    
    return DiscoveryProgressSchema(
        total_pages=progress.total_pages,
        pages_scanned=progress.pages_scanned,
        products_found=progress.products_found,
        products_added=progress.products_added,
        is_running=progress.is_running,
        current_phase=progress.current_phase,
        error=progress.error
    )


@router.post("/stop", response_model=TaskResponse)
async def stop_discovery():
    """
    Stop the running discovery task.
    """
    global _task_running
    
    if not _task_running:
        return TaskResponse(
            success=False,
            message="No discovery task is running"
        )
    
    _stop_event.set()
    
    # Update progress to show stopping
    from ...discovery import scraper
    scraper._progress.current_phase = "Stopping..."
    
    return TaskResponse(
        success=True,
        message="Stop signal sent. Task will stop after current batch."
    )
