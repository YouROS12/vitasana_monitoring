"""
Market Monitor Scheduler.
Runs the Mass Scanner in monitoring mode periodically or at fixed times.
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
        self.stop_event = threading.Event()
        
    def _get_next_run(self) -> datetime:
        """Calculate the next run time based on config."""
        mode = self.config.get('scheduler', 'mode', default='interval')
        now = datetime.now()
        
        if mode == 'fixed_times':
            times_list = self.config.get('scheduler', 'times')
            if not times_list:
                # Default fallback slots
                times_list = ["08:30", "12:30", "16:00", "19:30"]
                
            candidates = []
            today_str = now.strftime('%Y-%m-%d')
            
            for t_str in times_list:
                try:
                    dt = datetime.strptime(f"{today_str} {t_str}", "%Y-%m-%d %H:%M")
                    candidates.append(dt)
                except ValueError:
                    logger.error(f"Invalid time format in config: {t_str}")
            
            candidates.sort()
            
            # Find next slot today
            for cand in candidates:
                if cand > now:
                    return cand
            
            # If no more slots today, pick first slot tomorrow
            if candidates:
                tomorrow = now + timedelta(days=1)
                first = candidates[0]
                return first.replace(year=tomorrow.year, month=tomorrow.month, day=tomorrow.day)
                
            # Fallback if list empty
            return now + timedelta(hours=6)
            
        else:
            # Interval mode
            interval = self.config.get_int('scheduler', 'interval_hours', default=6)
            return now + timedelta(hours=interval)

    def run(self):
        """Start the scheduler loop."""
        mode = self.config.get('scheduler', 'mode', default='interval')
        logger.info(f"Starting Market Scheduler (Mode: {mode})")
        
        while not self.stop_event.is_set():
            next_run = self._get_next_run()
            logger.info(f"Next scan scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            
            while datetime.now() < next_run and not self.stop_event.is_set():
                time.sleep(1)
                
            if not self.stop_event.is_set():
                self._run_job()
                
    def _run_job(self):
        """Execute the monitoring scan."""
        try:
            logger.info(f"Starting scheduled scan at {datetime.now()}")
            
            # PHASE 1: REFRESH AUTHENTICATION
            # Force a fresh login to update config.yaml with valid cookies
            try:
                from ..auth.session import create_auth_session_from_config
                auth = create_auth_session_from_config()
                logger.info("Refreshing session cookies...")
                if auth.refresh_cookies():
                    logger.info("Authentication refreshed successfully.")
                else:
                    logger.warning("Cookie refresh returned False - checking credentials might be needed.")
            except Exception as e:
                logger.error(f"Auth refresh failed: {e}")
            
            # PHASE 2: RUN SCANNER
            scanner = MassScanner()
            scanner.scan(optimized=True)
            logger.info("Scheduled scan complete.")
        except Exception as e:
            logger.error(f"Error in scheduled scan: {e}")
            
    def stop(self):
        """Stop the scheduler."""
        logger.info("Stopping scheduler...")
        self.stop_event.set()
