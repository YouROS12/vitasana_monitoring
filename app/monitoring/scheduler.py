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
        self.last_discovery_date = None
        self._last_discovery_date = None
        self._last_summary_date = None
        self._last_analysis_date = None
        
        self._last_analysis_date = None
        
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

    def _should_run_analysis(self) -> bool:
        """Check if analysis should run (e.g., at 04:00)."""
        now = datetime.now()
        target_str = self.config.get('analysis', 'daily_time', default='04:00')
        
        try:
            target_time = datetime.strptime(target_str, '%H:%M').time()
            if now.time() >= target_time and (not self._last_analysis_date or self._last_analysis_date < now.date()):
                return True
            return False
        except ValueError:
            return False

    def _run_analysis_job(self):
        """Run the heavy analytics job."""
        try:
            from app.analysis.engine import GoldMineAnalyzer
            logger.info("Running scheduled analytics...")
            
            analyzer = GoldMineAnalyzer()
            analyzer.run_full_analysis()
            
            self._last_analysis_date = datetime.now().date()
            logger.info("Analytics job complete.")
            
        except Exception as e:
            logger.error(f"Analytics job failed: {e}")

    def run(self):
        """Start the scheduler loop."""
        mode = self.config.get('scheduler', 'mode', default='interval')
        logger.info(f"Starting Market Scheduler (Mode: {mode})")
        
        # Initial Check: Run analysis if missing
        try:
            from pathlib import Path
            if not Path("data/analytics/gold_mine_latest.json").exists():
                logger.info("No analytics found. Running initial analysis...")
                self._run_analysis_job()
        except Exception:
            pass
        
        while not self.stop_event.is_set():
            # Check for weekly discovery
            if self._should_run_discovery():
                self._run_discovery_job()
            
            # Check for daily analysis
            if self._should_run_analysis():
                self._run_analysis_job()
            
            # Check for daily summary
            if self._should_send_daily_summary():
                self._send_daily_summary()
            
            next_run = self._get_next_run()
            logger.info(f"Next scan scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            
            while datetime.now() < next_run and not self.stop_event.is_set():
                time.sleep(60) 
                
                if self._should_run_discovery():
                    self._run_discovery_job()
                    
                if self._should_run_analysis():
                    self._run_analysis_job()
                    
                if self._should_send_daily_summary():
                    self._send_daily_summary()
                    
                # Run order sync frequently (every minute)
                self._sync_orders_and_notify()
                
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

    def _sync_orders_and_notify(self):
        """Sync orders from WooCommerce and notify on new orders."""
        try:
            from ..core.database import get_database
            from app.orders.service import OrderService
            from app.services.telegram import create_notifier_from_config
            
            db = get_database()
            notifier = create_notifier_from_config()
            
            # Get existing order IDs (processing only) BEFORE sync to identify new ones
            existing_ids = set()
            try:
                existing_ids = db.get_order_ids(status='processing')
            except Exception as e:
                logger.error(f"Failed to fetch existing IDs: {e}")
            
            # Sync orders using OrderService (handles persistence correctly)
            try:
                service = OrderService()
                # We skip live check (check_stock=False) for speed in the scheduler background job
                synced_orders = service.sync_orders(status='processing', check_stock=False)
                
                new_orders = []
                for order in synced_orders:
                    # If order ID was NOT in DB before sync, it's new
                    if order.get('id') not in existing_ids:
                        new_orders.append(order)
                
                # Notify about new orders
                if new_orders and notifier.enabled:
                    logger.info(f"Found {len(new_orders)} new orders to notify.") 
                    for order in new_orders:
                        billing = order.get('billing', {})
                        customer = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip() or "Guest"
                        city = billing.get('city', 'Unknown')
                        phone = billing.get('phone', 'Unknown')
                        total = order.get('total_amount', 0)
                        items = order.get('items', [])
                        item_count = sum(item.get('quantity', 1) for item in items)
                        
                        message = f"""
🛒 <b>NEW ORDER #{order.get('number')}</b>

👤 Customer: {customer}
📍 City: {city}
📞 Phone: {phone}
📦 Items: {item_count}
💰 Total: {total:.2f} MAD
"""
                        notifier.send_message(message)
                    
                    logger.info(f"Notified about {len(new_orders)} new orders")
                    
            except Exception as e:
                logger.error(f"Order sync failed: {e}")
                
        except Exception as e:
            logger.error(f"Order notification error: {e}")

    def _should_send_daily_summary(self) -> bool:
        """Check if daily summary should be sent."""
        now = datetime.now()
        summary_time = self.config.get('notifications', 'daily_summary_time', default='20:00')
        
        try:
            hour, minute = map(int, summary_time.split(':'))
            # Check if it's the summary time (within 5 minutes window)
            if now.hour == hour and now.minute >= minute and now.minute < minute + 5:
                # Check if already sent today
                if hasattr(self, '_last_summary_date') and self._last_summary_date == now.date():
                    return False
                return True
        except:
            pass
        return False

    def _send_daily_summary(self):
        """Send daily summary notification with top products."""
        try:
            from ..core.database import get_database
            from app.services.telegram import create_notifier_from_config
            import pandas as pd
            
            self._last_summary_date = datetime.now().date()
            
            db = get_database()
            notifier = create_notifier_from_config()
            
            if not notifier.enabled:
                return
            
            # Gather basic stats
            try:
                products = db.get_latest_statuses()
                product_count = len(products) if products else 0
                
                orders = db.get_orders_history(limit=50)
                today = datetime.now().date()
                todays_orders = [o for o in orders if o.get('date_created', '').startswith(str(today))]
                order_count = len(todays_orders)
                order_total = sum(float(o.get('total_amount', 0) or 0) for o in todays_orders)
                
            except Exception as e:
                logger.error(f"Error gathering summary stats: {e}")
                product_count = 0
                order_count = 0
                order_total = 0
            
            # Get top 10 Gold Mine (by daily profit)
            gold_mine_text = ""
            try:
                history = db.get_stock_history_lite(hours=7*24)
                latest = db.get_latest_statuses()
                
                if history and latest:
                    df = pd.DataFrame(history)
                    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce', utc=True)
                    df = df.sort_values(['product_sku', 'timestamp'])
                    
                    velocity_map = {}
                    for sku, group in df.groupby('product_sku'):
                        if len(group) >= 2:
                            group = group.sort_values('timestamp')
                            group['prev_stock'] = group['stock'].shift(1)
                            group['diff'] = group['prev_stock'] - group['stock']
                            sales = group[group['diff'] > 0]['diff'].sum()
                            if sales > 0:
                                velocity_map[sku] = sales / 7
                    
                    gold_products = []
                    for item in latest:
                        sku = item['sku']
                        velocity = velocity_map.get(sku, 0)
                        price = float(item.get('price') or 0)
                        final = float(item.get('final_price') or 0)
                        margin = price - final if final > 0 else 0
                        daily_profit = velocity * margin
                        
                        if daily_profit >= 10:
                            gold_products.append({
                                'name': item['name'][:30],
                                'profit': daily_profit
                            })
                    
                    gold_products.sort(key=lambda x: x['profit'], reverse=True)
                    top_gold = gold_products[:10]
                    
                    if top_gold:
                        gold_mine_text = "\n\n<b>💰 TOP 10 GOLD MINE</b>\n"
                        for i, p in enumerate(top_gold, 1):
                            gold_mine_text += f"{i}. {p['name']} - {p['profit']:.0f} MAD/day\n"
                            
            except Exception as e:
                logger.error(f"Gold Mine calc failed: {e}")
            
            # Get top 10 Market Pulse (by velocity/24h)
            pulse_text = ""
            try:
                history_24h = db.get_stock_history_lite(hours=24)
                if history_24h:
                    df24 = pd.DataFrame(history_24h)
                    df24['timestamp'] = pd.to_datetime(df24['timestamp'], errors='coerce', utc=True)
                    df24 = df24.sort_values(['product_sku', 'timestamp'])
                    
                    movers = []
                    for sku, group in df24.groupby('product_sku'):
                        if len(group) >= 2:
                            start_stock = group.iloc[0]['stock']
                            end_stock = group.iloc[-1]['stock']
                            drop = start_stock - end_stock
                            if drop > 0:
                                name = latest_map.get(sku, {}).get('name', f'SKU {sku}') if 'latest_map' in dir() else f'SKU {sku}'
                                # Get name from latest
                                for item in latest:
                                    if item['sku'] == sku:
                                        name = item['name'][:30]
                                        break
                                movers.append({'name': name, 'units': int(drop)})
                    
                    movers.sort(key=lambda x: x['units'], reverse=True)
                    top_movers = movers[:10]
                    
                    if top_movers:
                        pulse_text = "\n\n<b>🔥 TOP 10 MOVERS (24h)</b>\n"
                        for i, m in enumerate(top_movers, 1):
                            pulse_text += f"{i}. {m['name']} - {m['units']} units\n"
                            
            except Exception as e:
                logger.error(f"Market Pulse calc failed: {e}")
            
            message = f"""
📊 <b>DAILY SUMMARY - {datetime.now().strftime('%d/%m/%Y')}</b>

🛒 Orders Today: <b>{order_count}</b>
💰 Revenue: <b>{order_total:.2f} MAD</b>
📦 Products Monitored: {product_count:,}
{gold_mine_text}{pulse_text}
Good night! 🌙
"""
            notifier.send_message(message)
            logger.info("Daily summary sent")
            
        except Exception as e:
            logger.error(f"Daily summary error: {e}")
            
    def stop(self):
        """Stop the scheduler."""
        logger.info("Stopping scheduler...")
        self.stop_event.set()
