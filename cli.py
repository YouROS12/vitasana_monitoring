"""
CLI for Vitasana Monitoring.
Run discovery, monitoring, or start the server from command line.
"""

import sys
import argparse
from pathlib import Path

# Add project to path
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def cmd_discover(args):
    """Run product discovery."""
    from app.core.config import get_config
    from app.core.logging import setup_logging
    from app.discovery.scraper import run_discovery
    
    config = get_config()
    setup_logging(config.log_path, config.get('general', 'log_level', default='INFO'))
    
    print(f"[DISCOVERY] Starting discovery (pages {args.start}-{args.end})...")
    
    user_agents = config.get_list('scraper', 'user_agents')
    
    result = run_discovery(
        base_url=config.get('scraper', 'base_url'),
        start_page=args.start,
        end_page=args.end,
        user_agents=user_agents,
        timeout=config.get_int('scraper', 'timeout', default=30),
        listing_workers=args.listing_workers,
        description_workers=args.desc_workers
    )
    
    print(f"\n[OK] Discovery complete!")
    print(f"   Pages scanned: {result.pages_scanned}")
    print(f"   Products found: {result.products_found}")
    print(f"   Products added: {result.products_added}")


def cmd_monitor(args):
    """Run stock monitoring."""
    from app.core.config import get_config
    from app.core.logging import setup_logging
    from app.monitoring.tracker import run_monitoring
    from app.auth.session import create_auth_session_from_config
    
    config = get_config()
    setup_logging(config.log_path, config.get('general', 'log_level', default='INFO'))
    
    keywords = [k.strip() for k in args.keywords.split(',')] if args.keywords else None
    
    print(f"[MONITOR] Starting monitoring (limit={args.limit}, keywords={keywords})...")
    
    auth = create_auth_session_from_config()
    
    # Get client_id from first credential
    creds = config.get('credentials', default=[])
    client_id = creds[0].get('client_id') if creds else ''
    
    result = run_monitoring(
        auth_session=auth,
        get_product_url=config.get('api', 'get_product_url'),
        filter_product_url=config.get('api', 'filter_product_url'),
        client_id=client_id,
        timeout=config.get_int('api', 'timeout', default=25),
        limit=args.limit,
        offset=args.offset,
        keywords=keywords,
        workers=args.workers,
        retry_count=config.get_int('api', 'retry_count', default=3)
    )
    
    print(f"\n[OK] Monitoring complete!")
    print(f"   Products processed: {result.products_processed}")
    print(f"   Products updated: {result.products_updated}")
    print(f"   Products failed: {result.products_failed}")


def cmd_serve(args):
    """Start the API server."""
    import uvicorn
    
    print(f"[SERVER] Starting API server on http://{args.host}:{args.port}")
    print(f"   Docs: http://{args.host}:{args.port}/docs")
    
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )


def cmd_dashboard(args):
    """Start the Streamlit dashboard."""
    import subprocess
    
    print("[DASHBOARD] Starting dashboard...")
    print("   Note: Make sure the API server is running first!")
    
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        str(project_root / "dashboard.py"),
        "--server.port", str(args.port)
    ])


def cmd_auth_refresh(args):
    """Login and save fresh cookies to config."""
    from app.core.config import get_config
    from app.core.logging import setup_logging
    from app.auth.session import create_auth_session_from_config
    
    config = get_config()
    setup_logging(config.log_path, config.get('general', 'log_level', default='INFO'))
    
    print(f"[AUTH] Refreshing cookies...")
    
    auth = create_auth_session_from_config()
    
    if auth.refresh_cookies(credential_index=args.account):
        print(f"[OK] Cookies refreshed and saved to config.yaml!")
        print(f"   You can now run monitoring.")
    else:
        print(f"[ERROR] Failed to refresh cookies. Check your credentials.")


def cmd_scan(args):
    """Run mass market scan."""
    from app.core.config import get_config
    from app.core.logging import setup_logging
    from app.discovery.mass_scanner import MassScanner
    
    config = get_config()
    setup_logging(config.log_path, config.get('general', 'log_level', default='INFO'))
    
    scanner = MassScanner()
    if args.monitor:
        scanner.scan(optimized=True)
    else:
        scanner.scan(optimized=False)


def cmd_optimize(args):
    """Run market optimizer."""
    from app.core.config import get_config
    from app.core.logging import setup_logging
    from app.monitoring.optimizer import MarketOptimizer
    
    config = get_config()
    setup_logging(config.log_path, config.get('general', 'log_level', default='INFO'))
    
    optimizer = MarketOptimizer()
    prefixes = optimizer.save_optimized_list()
    print(f"\n[OK] Optimization complete. Saved {len(prefixes)} prefixes.")


def cmd_schedule(args):
    """Run market scheduler."""
    from app.core.config import get_config
    from app.core.logging import setup_logging
    from app.monitoring.scheduler import MarketScheduler
    
    config = get_config()
    setup_logging(config.log_path, config.get('general', 'log_level', default='INFO'))
    
    scheduler = MarketScheduler()
    try:
        scheduler.run()
    except KeyboardInterrupt:
        scheduler.stop()


def main():
    parser = argparse.ArgumentParser(
        description="Vitasana Monitoring CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py discover --start 1 --end 100
  python cli.py monitor --limit 500 --keywords "vitamin,paracetamol"
  python cli.py serve
  python cli.py dashboard
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Discovery command
    discover_parser = subparsers.add_parser("discover", help="Run product discovery")
    discover_parser.add_argument("--start", type=int, default=1, help="Start page")
    discover_parser.add_argument("--end", type=int, default=100, help="End page")
    discover_parser.add_argument("--listing-workers", type=int, default=4, help="Listing page workers")
    discover_parser.add_argument("--desc-workers", type=int, default=8, help="Description workers")
    
    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Run stock monitoring")
    monitor_parser.add_argument("--limit", type=int, default=None, help="Max products to process")
    monitor_parser.add_argument("--offset", type=int, default=0, help="Skip first N products")
    monitor_parser.add_argument("--keywords", type=str, default=None, help="Comma-separated keywords")
    monitor_parser.add_argument("--workers", type=int, default=5, help="Concurrent workers")
    
    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start API server")
    serve_parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    
    # Dashboard command
    dashboard_parser = subparsers.add_parser("dashboard", help="Start Streamlit dashboard")
    dashboard_parser.add_argument("--port", type=int, default=8501, help="Dashboard port")
    
    # Auth command
    auth_parser = subparsers.add_parser("auth", help="Authentication commands")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command")
    
    refresh_parser = auth_subparsers.add_parser("refresh", help="Login and save cookies")
    refresh_parser.add_argument("--account", type=int, default=0, help="Account index (0 or 1)")
    
    
    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Run mass market recursive scan")
    scan_parser.add_argument("--monitor", action="store_true", help="Use optimized queries (Monitoring Mode)")
    
    # Optimize command
    optimize_parser = subparsers.add_parser("optimize", help="Generate optimized search queries from DB")
    
    # Schedule command
    schedule_parser = subparsers.add_parser("schedule", help="Run periodic market monitoring")
    
    args = parser.parse_args()
    
    if args.command == "discover":
        cmd_discover(args)
    elif args.command == "monitor":
        cmd_monitor(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "dashboard":
        cmd_dashboard(args)
    elif args.command == "auth":
        if args.auth_command == "refresh":
            cmd_auth_refresh(args)
        else:
            auth_parser.print_help()
    elif args.command == "scan":
        cmd_scan(args)
    elif args.command == "optimize":
        cmd_optimize(args)
    elif args.command == "schedule":
        cmd_schedule(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
