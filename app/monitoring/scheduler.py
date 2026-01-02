"""
Market Monitor Scheduler.
Runs the Mass Scanner in monitoring mode periodically (e.g. every 6 hours).
"""

import time
import logging
import threading
from datetime import datetime, timedelta

from ..core.config import get_config
from ..discovery.mass_scanner import MassScanner

logger = logging.getLogger(__name__)

class MarketScheduler:
    def __init__(self):
        self.config = get_config()
        self.interval_hours = self.config.get_int('scheduler', 'interval_hours', default=6)
        self.stop_event = threading.Event()
        
    def run(self):
        """Start the scheduler loop."""
        logger.info(f"Starting Market Scheduler (Interval: {self.interval_hours} hours)")
        
        # Run immediately on start? Yes, user probably wants feedback.
        self._run_job()
        
        while not self.stop_event.is_set():
            # rigorous wait loop to allow interruption
            next_run = datetime.now() + timedelta(hours=self.interval_hours)
            logger.info(f"Next scan scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            
            while datetime.now() < next_run and not self.stop_event.is_set():
                time.sleep(1)
                
            if not self.stop_event.is_set():
                self._run_job()
                
    def _run_job(self):
        """Execute the monitoring scan."""
        try:
            logger.info(f"Starting scheduled scan at {datetime.now()}")
            scanner = MassScanner()
            # Use optimized mode by default for monitoring
            scanner.scan(optimized=True)
            logger.info("Scheduled scan complete.")
        except Exception as e:
            logger.error(f"Error in scheduled scan: {e}")
            
    def stop(self):
        """Stop the scheduler."""
        logger.info("Stopping scheduler...")
        self.stop_event.set()
