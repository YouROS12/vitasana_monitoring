
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
