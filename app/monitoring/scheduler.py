"""
Market Monitor Scheduler.
Runs the Mass Scanner in monitoring mode periodically or at fixed times.
Also runs weekly product discovery + prefix optimization.
"""

import time
import logging
import threading
import json
from datetime import datetime, timedelta
from pathlib import Path

from ..core.config import get_config
from ..discovery.mass_scanner import MassScanner

logger = logging.getLogger(__name__)

class MarketScheduler:
    def __init__(self):
        self.config = get_config()
        self.stop_event = threading.Event()
        self.last_discovery_date = None  # Track when discovery last ran
        
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

    def _should_run_discovery(self) -> bool:
        """Check if weekly discovery should run."""
        now = datetime.now()
        
        # Get config (default: Sunday at 06:00)
        discovery_day = self.config.get('scheduler', 'discovery_day', default='sunday').lower()
        discovery_time = self.config.get('scheduler', 'discovery_time', default='06:00')
        
        # Map day name to weekday number
        days_map = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                    'friday': 4, 'saturday': 5, 'sunday': 6}
        target_weekday = days_map.get(discovery_day, 6)
        
        # Check if today is the right day
        if now.weekday() != target_weekday:
            return False
        
        # Check if we already ran discovery today
        if self.last_discovery_date == now.date():
            return False
        
        # Check if it's after the discovery time
        try:
            disc_hour, disc_min = map(int, discovery_time.split(':'))
            if now.hour < disc_hour or (now.hour == disc_hour and now.minute < disc_min):
                return False
        except:
            pass
        
        return True

    def run(self):
        """Start the scheduler loop."""
        mode = self.config.get('scheduler', 'mode', default='interval')
        logger.info(f"Starting Market Scheduler (Mode: {mode})")
        
        while not self.stop_event.is_set():
            # Check for weekly discovery first
            if self._should_run_discovery():
                self._run_discovery_job()
            
            next_run = self._get_next_run()
            logger.info(f"Next scan scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            
            while datetime.now() < next_run and not self.stop_event.is_set():
                time.sleep(1)
                # Re-check for discovery during wait
                if self._should_run_discovery():
                    self._run_discovery_job()
                
            if not self.stop_event.is_set():
                self._run_job()
                
    def _run_job(self):
        """Execute the monitoring scan (optimized, uses prefix list)."""
        try:
            logger.info(f"Starting scheduled scan at {datetime.now()}")
            
            # PHASE 1: REFRESH AUTHENTICATION
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

    def _run_discovery_job(self):
        """Execute weekly product discovery + prefix optimization."""
        try:
            logger.info("=" * 50)
            logger.info("WEEKLY DISCOVERY: Starting full product discovery...")
            logger.info("=" * 50)
            
            self.last_discovery_date = datetime.now().date()
            
            # PHASE 1: REFRESH AUTHENTICATION
            try:
                from ..auth.session import create_auth_session_from_config
                auth = create_auth_session_from_config()
                auth.refresh_cookies()
            except Exception as e:
                logger.error(f"Auth refresh failed: {e}")
            
            # PHASE 2: FULL DISCOVERY (non-optimized, finds new products)
            scanner = MassScanner()
            scanner.scan(optimized=False)  # Full recursive scan
            
            # PHASE 3: OPTIMIZE PREFIXES
            logger.info("Optimizing search prefixes...")
            self._optimize_prefixes()
            
            logger.info("Weekly discovery complete!")
            
        except Exception as e:
            logger.error(f"Error in discovery job: {e}")

    def _optimize_prefixes(self):
        """Generate optimized prefix list from scan results."""
        try:
            from ..core.database import get_database
            db = get_database()
            
            # Get effective prefixes (those that returned results)
            prefixes = db.get_effective_prefixes()
            
            if prefixes:
                # Save to JSON
                output_path = Path("data/optimized_prefixes.json")
                output_path.parent.mkdir(exist_ok=True)
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(prefixes, f, ensure_ascii=False, indent=2)
                
                logger.info(f"Saved {len(prefixes)} optimized prefixes to {output_path}")
        except Exception as e:
            logger.error(f"Prefix optimization failed: {e}")
            
    def stop(self):
        """Stop the scheduler."""
        logger.info("Stopping scheduler...")
        self.stop_event.set()
