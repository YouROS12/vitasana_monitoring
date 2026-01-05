
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
        
        # Build one row per ORDER (not per item)
        order_rows = []
        for order in orders:
            billing = order.get('billing', {})
            cust_name = f"{billing.get('first_name','')} {billing.get('last_name','')}".strip() or "Guest"
            city = billing.get('city', '-')
            
            # Fulfillment indicator
            fulfill = order.get('fulfillability', 'unknown')
            status_symbol = {'ready': '✅', 'partial': '⚠️', 'out_of_stock': '❌'}.get(fulfill, '❓')
            
            # Count items
            items = order.get('items', [])
            item_count = sum(item.get('quantity', 1) for item in items)
            
            order_rows.append({
                "Status": status_symbol,
                "Order #": order.get('number', '-'),
                "Date": order.get('date_created', '').split('T')[0],
                "Customer": cust_name,
                "City": city,
                "Items": item_count,
                "Total": f"{order.get('total_amount', 0):.2f} MAD",
                "Fulfillability": fulfill.capitalize() if fulfill else "Unknown"
            })
        
        if order_rows:
            df = pd.DataFrame(order_rows)
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Status": st.column_config.TextColumn("", width="small"),
                    "Order #": st.column_config.TextColumn("Order #", width="small"),
                    "Date": st.column_config.TextColumn("Date", width="small"),
                    "Customer": st.column_config.TextColumn("Customer", width="medium"),
                    "City": st.column_config.TextColumn("City", width="medium"),
                    "Items": st.column_config.NumberColumn("Items", width="small"),
                    "Total": st.column_config.TextColumn("Total", width="small"),
                    "Fulfillability": st.column_config.TextColumn("Status", width="small")
                }
            )
            
            # Order details expander
            st.markdown("---")
            st.subheader("Order Details")
            order_numbers = [o.get('number') for o in orders]
            selected_order = st.selectbox("Select order to view details:", order_numbers)
            
            if selected_order:
                order_data = next((o for o in orders if o.get('number') == selected_order), None)
                if order_data and order_data.get('items'):
                    item_rows = []
                    for item in order_data['items']:
                        item_rows.append({
                            "Product": item.get('name', 'Unknown'),
                            "Qty": item.get('quantity', 0),
                            "Stock": item.get('available_qty', 0),
                            "Status": item.get('stock_status', 'unknown'),
                            "Match": item.get('match_status', 'none')
                        })
                    st.dataframe(pd.DataFrame(item_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No orders data.")
            
    else:
        st.info("No orders found in history. Click 'Sync Now' to fetch.")
