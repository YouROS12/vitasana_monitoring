"""
Monitoring task API endpoints.
"""

from fastapi import APIRouter, BackgroundTasks
import threading
from typing import Optional, List

from ..schemas import MonitoringRequest, MonitoringProgress as MonitoringProgressSchema, TaskResponse
from ...monitoring.tracker import run_monitoring, get_progress

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

# Track running task
_task_lock = threading.Lock()
_task_running = False
_stop_event = threading.Event()


def _run_monitoring_task(limit: Optional[int], offset: int, keywords: Optional[List[str]], workers: int):
    """Background task runner for monitoring."""
    global _task_running
    
    from ...monitoring import tracker
    from ...core.config import get_config
    from ...auth.session import create_auth_session_from_config
    
    config = get_config()
    auth = create_auth_session_from_config()
    _stop_event.clear()
    
    try:
        # Smart Switching: Use Optimized MassScanner for full scans
        # Criteria: No keywords, and Limit is None (All) or very large (>2000)
        use_optimized = (keywords is None) and (limit is None or limit > 2000)
        
        if use_optimized:
             from ...discovery.mass_scanner import MassScanner
             # Initialize progress
             tracker._progress.is_running = True
             tracker._progress.current_phase = "Initializing Optimized Scan"
             tracker._progress.total_products = 0 # Will update dynamically
             tracker._progress.products_processed = 0
             tracker._progress.products_failed = 0
             
             scanner = MassScanner()
             
             # Adapter to update global progress
             def progress_adapter(phase, items_found, prefixes_done, prefixes_total):
                 tracker._progress.current_phase = phase
                 # Map prefixes to processed/total so the progress bar works
                 tracker._progress.products_processed = prefixes_done 
                 tracker._progress.total_products = prefixes_total
                 # Map items found to updated count
                 tracker._progress.products_updated = items_found 
                 
             scanner.scan(optimized=True, progress_callback=progress_adapter)
             
             tracker._progress.current_phase = "Complete"
             tracker._progress.is_running = False
             return

        # Fallback to Linear Tracker for specific/small scans
        # Get client_id from first credential in config
        creds = config.get('credentials', default=[])
        client_id = creds[0].get('client_id') if creds else ''
        
        tracker.run_monitoring(
            auth_session=auth,
            get_product_url=config.get('api', 'get_product_url'),
            filter_product_url=config.get('api', 'filter_product_url'),
            client_id=client_id,
            timeout=config.get_int('api', 'timeout', default=25),
            limit=limit,
            offset=offset,
            keywords=keywords,
            workers=workers,
            retry_count=config.get_int('api', 'retry_count', default=3),
            stop_event=_stop_event
        )
    finally:
        with _task_lock:
            global _task_running
            _task_running = False


@router.post("/run", response_model=TaskResponse)
async def run_monitoring_endpoint(
    request: MonitoringRequest,
    background_tasks: BackgroundTasks
):
    """
    Start a product monitoring task.
    """
    global _task_running
    
    with _task_lock:
        if _task_running:
            return TaskResponse(
                success=False,
                message="Monitoring is already running"
            )
        _task_running = True
    
    # Parse keywords
    keywords = None
    if request.keywords:
        keywords = [k.strip() for k in request.keywords.split(',') if k.strip()]
    
    background_tasks.add_task(
        _run_monitoring_task,
        request.limit,
        request.offset,
        keywords,
        request.workers
    )
    
    limit_str = f"limit={request.limit}" if request.limit else "all products"
    keywords_str = f", keywords={keywords}" if keywords else ""
    
    return TaskResponse(
        success=True,
        message=f"Monitoring started ({limit_str}{keywords_str})"
    )


@router.get("/status", response_model=MonitoringProgressSchema)
async def get_monitoring_status():
    """
    Get current monitoring progress.
    """
    progress = get_progress()
    
    return MonitoringProgressSchema(
        total_products=progress.total_products,
        products_processed=progress.products_processed,
        products_updated=progress.products_updated,
        products_failed=progress.products_failed,
        is_running=progress.is_running,
        current_phase=progress.current_phase,
        error=progress.error
    )


@router.post("/stop", response_model=TaskResponse)
async def stop_monitoring():
    """
    Stop the running monitoring task.
    """
    global _task_running
    
    if not _task_running:
        return TaskResponse(
            success=False,
            message="No monitoring task is running"
        )
    
    _stop_event.set()
    
    # Update progress to show stopping
    from ...monitoring import tracker
    tracker._progress.current_phase = "Stopping..."
    
    return TaskResponse(
        success=True,
        message="Stop signal sent. Task will stop after current batch."
    )
