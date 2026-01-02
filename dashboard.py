"""
Streamlit Dashboard for Vitasana Monitoring.
A clean UI to run and monitor tasks with configurable parameters.
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import time
from pathlib import Path

# Configuration
API_BASE_URL = "http://localhost:8000/api"
LOG_FILE = Path(__file__).parent / "vitasana.log"

# Page config
st.set_page_config(
    page_title="Vitasana Monitoring",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .stProgress > div > div > div > div {
        background-color: #00d4aa;
    }
    .task-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 12px;
        color: white;
        margin-bottom: 10px;
    }
    .metric-card {
        background: #f8f9fa;
        padding: 15px;
        border-radius: 8px;
        text-align: center;
    }
    .status-running {
        color: #ffc107;
        font-weight: bold;
    }
    .status-complete {
        color: #28a745;
        font-weight: bold;
    }
    .status-failed {
        color: #dc3545;
        font-weight: bold;
    }
    .log-viewer {
        background-color: #1e1e1e;
        color: #d4d4d4;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 12px;
        padding: 15px;
        border-radius: 8px;
        height: 300px;
        overflow-y: auto;
        white-space: pre-wrap;
        word-wrap: break-word;
    }
    .stat-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 15px;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .stat-box h2 {
        margin: 0;
        font-size: 28px;
    }
    .stat-box p {
        margin: 5px 0 0 0;
        opacity: 0.8;
    }
</style>
""", unsafe_allow_html=True)


def api_request(method: str, endpoint: str, **kwargs):
    """Make an API request with error handling."""
    try:
        url = f"{API_BASE_URL}{endpoint}"
        response = requests.request(method, url, timeout=60, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to API. Make sure the server is running: `python cli.py serve`")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"❌ API Error: {e}")
        return None
    except Exception as e:
        st.error(f"❌ Error: {e}")
        return None


def get_recent_logs(num_lines: int = 50) -> str:
    """Read the last N lines from the log file."""
    try:
        if not LOG_FILE.exists():
            return "No logs yet..."
        
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            recent = lines[-num_lines:] if len(lines) > num_lines else lines
            return ''.join(recent)
    except Exception as e:
        return f"Error reading logs: {e}"


def render_progress_bar(current: int, total: int, label: str = ""):
    """Render a progress bar."""
    if total > 0:
        progress = current / total
        st.progress(progress)
        st.caption(f"{label}: {current}/{total} ({progress*100:.1f}%)")
    else:
        st.progress(0.0)
        st.caption(f"{label}: Waiting...")


def render_discovery_status():
    """Render discovery task status."""
    status = api_request("GET", "/discovery/status")
    if not status:
        return False, status
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📄 Pages Scanned", f"{status['pages_scanned']}/{status['total_pages']}")
    with col2:
        st.metric("🔍 Products Found", status['products_found'])
    with col3:
        st.metric("✅ Products Added", status['products_added'])
    with col4:
        if status['is_running']:
            st.markdown('<span class="status-running">🔄 RUNNING</span>', unsafe_allow_html=True)
        elif status['error']:
            st.markdown('<span class="status-failed">❌ FAILED</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-complete">✅ COMPLETE</span>', unsafe_allow_html=True)
    
    if status['total_pages'] > 0:
        render_progress_bar(status['pages_scanned'], status['total_pages'], "Progress")
    
    st.caption(f"Phase: {status['current_phase']}")
    
    if status['error']:
        st.error(status['error'])
    
    return status['is_running'], status


def render_monitoring_status():
    """Render monitoring task status."""
    status = api_request("GET", "/monitoring/status")
    if not status:
        return False, status
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📦 Total Products", status['total_products'])
    with col2:
        st.metric("✅ Updated", status['products_updated'])
    with col3:
        st.metric("❌ Failed", status['products_failed'])
    with col4:
        if status['is_running']:
            st.markdown('<span class="status-running">🔄 RUNNING</span>', unsafe_allow_html=True)
        elif status['error']:
            st.markdown('<span class="status-failed">❌ FAILED</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-complete">✅ COMPLETE</span>', unsafe_allow_html=True)
    
    if status['total_products'] > 0:
        render_progress_bar(
            status['products_processed'],
            status['total_products'],
            "Processing"
        )
    
    st.caption(f"Phase: {status['current_phase']}")
    
    if status['error']:
        st.error(status['error'])
    
    return status['is_running'], status


# ==================== SIDEBAR ====================
st.sidebar.title("💊 Vitasana")
st.sidebar.markdown("---")

# Check API connection
health = api_request("GET", "/health")
if health:
    st.sidebar.success(f"✅ API Connected")
    st.sidebar.caption(f"📦 Products: {health['database_products']:,}")
    st.sidebar.caption(f"📊 Records: {health['database_records']:,}")
else:
    st.sidebar.error("❌ API Offline")
    health = {}

st.sidebar.markdown("---")

# Navigation
page = st.sidebar.radio(
    "Navigation",
    ["🎮 Task Runner", "📦 Products", "🛒 Orders", "📊 Analytics", "📋 Logs"],
    label_visibility="collapsed"
)


# ==================== TASK RUNNER PAGE ====================
if page == "🎮 Task Runner":
    st.title("🎮 Task Runner")
    st.markdown("Configure and run discovery or monitoring tasks with custom parameters.")
    
    # Quick Stats Row
    if health:
        st.markdown("### 📊 Quick Stats")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"""
            <div class="stat-box">
                <h2>{health.get('database_products', 0):,}</h2>
                <p>Total Products</p>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class="stat-box">
                <h2>{health.get('database_records', 0):,}</h2>
                <p>Monitoring Records</p>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            # Discovery status
            disc_status = api_request("GET", "/discovery/status")
            disc_state = "Running" if disc_status and disc_status.get('is_running') else "Idle"
            st.markdown(f"""
            <div class="stat-box">
                <h2>{disc_state}</h2>
                <p>Discovery Status</p>
            </div>
            """, unsafe_allow_html=True)
        with col4:
            # Monitoring status
            mon_status = api_request("GET", "/monitoring/status")
            mon_state = "Running" if mon_status and mon_status.get('is_running') else "Idle"
            st.markdown(f"""
            <div class="stat-box">
                <h2>{mon_state}</h2>
                <p>Monitoring Status</p>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
    
    tab1, tab2 = st.tabs(["🔍 Product Discovery", "📊 Stock Monitoring"])
    
    # ==================== DISCOVERY TAB ====================
    with tab1:
        st.header("🔍 Product Discovery")
        st.markdown("Scrape the public website to discover new products.")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("⚙️ Configuration")
            
            c1, c2 = st.columns(2)
            with c1:
                discovery_start = st.number_input(
                    "Start Page",
                    min_value=1,
                    value=1,
                    step=1,
                    help="First page to scan"
                )
            with c2:
                discovery_end = st.number_input(
                    "End Page",
                    min_value=1,
                    value=100,
                    step=10,
                    help="Last page to scan"
                )
            
            c3, c4 = st.columns(2)
            with c3:
                listing_workers = st.slider(
                    "Listing Workers",
                    min_value=1,
                    max_value=10,
                    value=4,
                    help="Concurrent workers for listing pages"
                )
            with c4:
                desc_workers = st.slider(
                    "Description Workers",
                    min_value=1,
                    max_value=15,
                    value=8,
                    help="Concurrent workers for descriptions"
                )
            
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("🚀 Start Discovery", type="primary", use_container_width=True):
                    result = api_request("POST", "/discovery/run", json={
                        "start_page": discovery_start,
                        "end_page": discovery_end,
                        "listing_workers": listing_workers,
                        "description_workers": desc_workers
                    })
                    if result and result.get('success'):
                        st.success(result['message'])
                        time.sleep(1)
                        st.rerun()
                    elif result:
                        st.warning(result['message'])
            
            with btn_col2:
                if st.button("🛑 Stop Discovery", type="secondary", use_container_width=True):
                    result = api_request("POST", "/discovery/stop")
                    if result:
                        st.info(result.get('message', 'Stop requested'))
        
        with col2:
            st.subheader("📈 Status")
            is_running, _ = render_discovery_status()
            
            if is_running:
                if st.button("🔄 Refresh", key="refresh_discovery"):
                    st.rerun()
                time.sleep(2)
                st.rerun()
    
    # ==================== MONITORING TAB ====================
    with tab2:
        st.header("📊 Stock Monitoring")
        st.markdown("Monitor stock levels and prices using the API.")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("⚙️ Configuration")
            
            c1, c2 = st.columns(2)
            with c1:
                monitor_limit = st.number_input(
                    "Product Limit",
                    min_value=0,
                    value=0,
                    step=50,
                    help="Max products to monitor (0 = all)"
                )
            with c2:
                monitor_offset = st.number_input(
                    "Offset",
                    min_value=0,
                    value=0,
                    step=100,
                    help="Skip first N products"
                )
            
            monitor_keywords = st.text_input(
                "Keywords Filter",
                placeholder="e.g., paracetamol, vitamin c",
                help="Comma-separated keywords to filter products"
            )
            
            monitor_workers = st.slider(
                "Workers",
                min_value=1,
                max_value=15,
                value=5,
                help="Concurrent API workers"
            )
            
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("🚀 Start Monitoring", type="primary", use_container_width=True):
                    result = api_request("POST", "/monitoring/run", json={
                        "limit": monitor_limit if monitor_limit > 0 else None,
                        "offset": monitor_offset,
                        "keywords": monitor_keywords if monitor_keywords else None,
                        "workers": monitor_workers
                    })
                    if result and result.get('success'):
                        st.success(result['message'])
                        time.sleep(1)
                        st.rerun()
                    elif result:
                        st.warning(result['message'])
            
            with btn_col2:
                if st.button("🛑 Stop Monitoring", type="secondary", use_container_width=True):
                    result = api_request("POST", "/monitoring/stop")
                    if result:
                        st.info(result.get('message', 'Stop requested'))
        
        with col2:
            st.subheader("📈 Status")
            is_running, _ = render_monitoring_status()
            
            if is_running:
                if st.button("🔄 Refresh", key="refresh_monitoring"):
                    st.rerun()
                time.sleep(2)
                st.rerun()
    
    # ==================== LIVE LOGS SECTION ====================
    st.markdown("---")
    st.subheader("📋 Live Logs")
    
    log_col1, log_col2 = st.columns([4, 1])
    with log_col1:
        log_lines = st.slider("Lines to show", min_value=20, max_value=200, value=50, step=10)
    with log_col2:
        if st.button("🔄 Refresh Logs", use_container_width=True):
            st.rerun()
    
    logs = get_recent_logs(log_lines)
    st.markdown(f'<div class="log-viewer">{logs}</div>', unsafe_allow_html=True)


# ==================== PRODUCTS PAGE ====================
elif page == "📦 Products":
    st.title("📦 Product Database")
    
    # Search and filters
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search = st.text_input("🔍 Search", placeholder="Search by name or SKU...")
    with col2:
        limit = st.selectbox("Show", [25, 50, 100, 250, 500, "All"], index=1)
    with col3:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    
    # Fetch products
    limit_val = 100000 if limit == "All" else limit
    params = {"limit": limit_val}
    if search:
        params["search"] = search
    
    data = api_request("GET", "/products/latest", params=params)
    
    if data:
        df = pd.DataFrame(data)
        
        if not df.empty:
            # Clean HTML from availability field
            if 'availability' in df.columns:
                import re
                def clean_status(val):
                    if pd.isna(val) or val is None:
                        return "-"
                    # Remove HTML tags
                    clean = re.sub(r'<[^>]+>', '', str(val))
                    # Map common values to readable format
                    clean = clean.strip()
                    if 'disponible' in clean.lower():
                        return "✅ In Stock"
                    elif 'rupture' in clean.lower() or 'out' in clean.lower():
                        return "❌ Out of Stock"
                    elif 'indisponible' in clean.lower():
                        return "⚠️ Unavailable"
                    return clean if clean else "-"
                df['availability'] = df['availability'].apply(clean_status)
            
            # Format price columns
            if 'price' in df.columns:
                df['price'] = df['price'].apply(lambda x: f"{x:.2f} MAD" if pd.notna(x) else "-")
            if 'final_price' in df.columns:
                df['final_price'] = df['final_price'].apply(lambda x: f"{x:.2f} MAD" if pd.notna(x) else "-")
            if 'stock' in df.columns:
                df['stock'] = df['stock'].apply(lambda x: int(x) if pd.notna(x) else "-")
            if 'discount_percent' in df.columns:
                df['discount_percent'] = df['discount_percent'].apply(lambda x: f"{x:.0f}%" if pd.notna(x) else "-")
            
            # Select columns to display (added 'price' for selling price)
            display_cols = ['sku', 'name', 'stock', 'price', 'final_price', 'discount_percent', 'availability', 'last_monitored']
            display_cols = [c for c in display_cols if c in df.columns]
            
            st.dataframe(
                df[display_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "sku": st.column_config.NumberColumn("SKU", width="small"),
                    "name": st.column_config.TextColumn("Product Name", width="large"),
                    "stock": st.column_config.TextColumn("Stock", width="small"),
                    "price": st.column_config.TextColumn("Selling Price", width="small"),
                    "final_price": st.column_config.TextColumn("Final Price", width="small"),
                    "discount_percent": st.column_config.TextColumn("Discount", width="small"),
                    "availability": st.column_config.TextColumn("Status", width="medium"),
                    "last_monitored": st.column_config.TextColumn("Last Updated", width="medium"),
                }
            )
            
            st.caption(f"Showing {len(df)} products")
        else:
            st.info("No products found")
    else:
        st.warning("Could not load products")



# ==================== ORDERS PAGE ====================

# ==================== ORDERS PAGE ====================

# ==================== ORDERS PAGE ====================
elif page == "🛒 Orders":
    st.title("🛒 Orders Management")
    st.markdown("Sync and track WooCommerce orders.")
    
    # === Controls ===
    col1, col2, col3, col4 = st.columns([1.5, 1, 1, 1])
    with col1:
        order_status_filter = st.selectbox(
            "Status Filter",
            ["all", "processing", "pending", "on-hold", "completed"],
            index=0,
            format_func=lambda x: x.capitalize()
        )
    with col2:
        limit = st.selectbox("Show Last", [10, 20, 50, 100], index=1)
    
    with col3:
        if st.button("🔄 Sync Now", type="primary", use_container_width=True):
            with st.spinner("Syncing orders..."):
                filter_status = order_status_filter if order_status_filter != 'all' else 'any'
                orders = api_request("GET", "/orders/sync", params={"status": filter_status})
                if orders:
                    st.success(f"Synced {len(orders)} orders")
                    st.rerun()
                else:
                    st.warning("Sync failed or no orders found")
                    
    with col4:
        if st.button("📂 Load History", use_container_width=True):
            st.rerun()

    # === Fetch Data ===
    status_param = order_status_filter if order_status_filter != 'all' else None
    orders = api_request("GET", "/orders/history", params={"limit": limit, "status": status_param})
    
    if orders:
        st.markdown(f"### Recent Orders ({len(orders)})")
        
        flat_data = []
        for order in orders:
            customer = order.get('billing', {})
            cust_name = f"{customer.get('first_name','')} {customer.get('last_name','')}".strip() or "Guest"
            
            # Order color indicator
            fulfill = order.get('fulfillability', 'unknown')
            status_symbol = {'ready': '✅', 'partial': '⚠️', 'out_of_stock': '❌'}.get(fulfill, '❓')
            
            for item in order['items']:
                qty_ordered = item['quantity']
                qty_avail = item.get('available_qty', 0)
                progress = min(1.0, qty_avail / qty_ordered) if qty_ordered > 0 else 0
                
                flat_data.append({
                    "Order": f"{status_symbol} #{order['number']}",
                    "Date": order['date_created'].split('T')[0],
                    "Customer": cust_name,
                    "Product": item['name'],
                    "Qty": qty_ordered,
                    "Stock": qty_avail,
                    "Availability": progress,
                    "Item Status": item.get('stock_status', 'unknown'),
                    "Match": item.get('match_status', 'none')
                })
        
        if flat_data:
            df = pd.DataFrame(flat_data)
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Order": st.column_config.TextColumn("Order", width="small"),
                    "Date": st.column_config.TextColumn("Date", width="small"),
                    "Customer": st.column_config.TextColumn("Customer", width="medium"),
                    "Product": st.column_config.TextColumn("Product", width="large"),
                    "Qty": st.column_config.NumberColumn("Qty", width="small"),
                    "Stock": st.column_config.NumberColumn("Stock", width="small"),
                    "Availability": st.column_config.ProgressColumn(
                        "Availability",
                        format="%.0f%%",
                        min_value=0,
                        max_value=1,
                    ),
                    "Item Status": st.column_config.TextColumn("Status", width="small"),
                    "Match": st.column_config.TextColumn("Match", width="small"),
                }
            )
        else:
            st.info("No items found in orders.")
            
    else:
        st.info("No orders found in history. Click 'Sync Now' to fetch.")
elif page == "📊 Analytics":
    # Tabs
    tab_gold, tab_pulse = st.tabs(["💰 Gold Mine", "❤️ Market Pulse"])
    
    # ---------------------------------------------------------
    # TAB 1: GOLD MINE OPPORTUNITIES
    # ---------------------------------------------------------
    with tab_gold:
        st.header("Gold Mine Opportunities")
        st.info("Ranking Algorithm: Sales Velocity (Units/Day) × Supplier Discount")
        
        try:
            # Direct API call to new endpoint
            resp = requests.get(f"{API_BASE_URL}/analytics/opportunities?days=7", timeout=60)
            if resp.status_code == 200:
                opp_data = resp.json()
                opps = opp_data.get('opportunities', [])
                
                if opps:
                    df_opp = pd.DataFrame(opps)
                    
                    st.dataframe(
                        df_opp,
                        column_config={
                            "name": st.column_config.TextColumn("Product", width="large"),
                            "velocity": st.column_config.NumberColumn("Velocity (Day)", format="%.1f 📦"),
                            "discount_percent": st.column_config.ProgressColumn(
                                "Discount %", 
                                format="%.1f%%", 
                                min_value=0, 
                                max_value=100
                            ),
                            "price": st.column_config.NumberColumn("Buy Price", format="%.2f MAD"),
                            "stock": st.column_config.NumberColumn("Stock", help="Current Stock"),
                            "score": st.column_config.NumberColumn(
                                "Score", 
                                help="Higher is better (Velocity * Discount)", 
                                format="%.1f ⭐️"
                            )
                        },
                        hide_index=True,
                        use_container_width=True,
                        height=600
                    )
                else:
                    st.warning("No high-value opportunities found yet. Monitor needs about 2-3 days of data.")
            else:
                st.error("Failed to fetch opportunities from API.")
        except Exception as e:
            st.error(f"API Connection Error: {e}")

    # ---------------------------------------------------------
    # TAB 2: MARKET PULSE (Original)
    # ---------------------------------------------------------
    with tab_pulse:
        st.subheader("Real-time Market Pulse")
        pulse = api_request("GET", "/analytics/pulse", params={"hours": 24})
        
        if pulse:
            stats = pulse.get('stats', {})
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📦 Monitored Items", f"{stats.get('total_monitored', 0):,}")
            with col2:
                st.metric("🔥 24h Movers", f"{stats.get('movers_count', 0)}")
            with col3:
                st.metric("⚠️ Low Stock", f"{len(pulse.get('low_stock', []))}")
            with col4:
                st.metric("Last Updated", "Now")
                
            st.markdown("---")
            
            # Row 1: Fastest Movers
            st.subheader("🔥 Fastest Selling Products (Last 24h)")
            movers = pulse.get('fastest_movers', [])
            
            if movers:
                df_movers = pd.DataFrame(movers)
                st.dataframe(
                    df_movers,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "sku": st.column_config.NumberColumn("SKU", width="small"),
                        "name": st.column_config.TextColumn("Product", width="large"),
                        "sales_est": st.column_config.ProgressColumn(
                            "Est. Sales", 
                            format="%d units",
                            min_value=0, 
                            max_value=max([x['sales_est'] for x in movers]) if movers else 100
                        ),
                        "start_stock": st.column_config.NumberColumn("Start", width="small"),
                        "end_stock": st.column_config.NumberColumn("Current", width="small"),
                        "velocity": st.column_config.TextColumn("Velocity (daily)", width="small"),
                    }
                )
            else:
                st.info("No significant stock movement detected in the last 24h.")
                
            # Row 2: Low Stock
            st.subheader("⚠️ Low Stock Alert (< 10)")
            low_stock = pulse.get('low_stock', [])
            
            if low_stock:
                df_low = pd.DataFrame(low_stock)
                cols = ['sku', 'name', 'stock', 'price', 'last_monitored']
                df_low = df_low[[c for c in cols if c in df_low.columns]]
                
                st.dataframe(
                    df_low,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "sku": st.column_config.NumberColumn("SKU", width="small"),
                        "name": st.column_config.TextColumn("Product", width="large"),
                        "stock": st.column_config.TextColumn("Stock", width="small"),
                        "price": st.column_config.TextColumn("Price", width="small"),
                        "last_monitored": st.column_config.TextColumn("Last Checked", width="medium"),
                    }
                )
            else:
                st.success("No low stock items found.")
                
        else:
            st.warning("Could not load market pulse data.")
        
        st.markdown("---")
        
        # Row 3: Chart
        st.subheader("📉 Product Stock History")
        
        c1, c2 = st.columns([1, 3])
        with c1:
            sku_input = st.number_input("Enter SKU to Analyze", min_value=1, value=1, step=1)
            if st.button("Load Chart", use_container_width=True):
                history = api_request("GET", f"/products/{sku_input}/history")
                if history and history.get('history'):
                    st.session_state['chart_data'] = history
                else:
                    st.session_state['chart_data'] = None
                    st.warning("Product not found or no history.")
                    
        with c2:
            if 'chart_data' in st.session_state and st.session_state['chart_data']:
                h_data = st.session_state['chart_data']
                st.markdown(f"**{h_data['name']}** (SKU: {h_data['sku']})")
                
                df_hist = pd.DataFrame(h_data['history'])
                if not df_hist.empty:
                    try:
                        df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'], format='ISO8601', utc=True)
                    except Exception:
                        df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'], errors='coerce', utc=True)
                        
                    st.line_chart(df_hist.set_index('timestamp')['stock'])
                else:
                    st.info("No data points for chart.")


# ==================== LOGS PAGE ====================
elif page == "📋 Logs":
    st.title("📋 Application Logs")
    st.markdown("View real-time logs from the application.")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        log_lines = st.slider("Lines to show", min_value=50, max_value=500, value=100, step=50)
    with col2:
        auto_refresh = st.checkbox("Auto-refresh (5s)", value=False)
    with col3:
        if st.button("🔄 Refresh Now", use_container_width=True):
            st.rerun()
    
    # Log viewer
    logs = get_recent_logs(log_lines)
    
    # Use a code block for better readability
    st.code(logs, language="log")
    
    # Log file info
    if LOG_FILE.exists():
        size_kb = LOG_FILE.stat().st_size / 1024
        st.caption(f"📄 Log file: {LOG_FILE.name} ({size_kb:.1f} KB)")
    
    if auto_refresh:
        time.sleep(5)
        st.rerun()


# Footer
st.sidebar.markdown("---")
st.sidebar.caption("Vitasana Monitoring v1.0")
st.sidebar.caption(f"🕐 {datetime.now().strftime('%H:%M:%S')}")
