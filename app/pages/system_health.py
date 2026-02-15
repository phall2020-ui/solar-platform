"""
System Health Dashboard Widget.
Displays observability metrics and materialized view status.
"""

import streamlit as st


def render_system_health_widget():
    """Render a compact system health summary widget.
    
    Shows query performance, cache effectiveness, errors, and view refresh status.
    Designed to be embedded in the dashboard page.
    """
    from solar_platform.services.materialized_views import MaterializedViewsManager, views_manager
    from solar_platform.services.observability import metrics
    from app.config_compat import config
    
    stats = metrics.get_stats()
    
    with st.expander("🔧 System Health", expanded=False):
        # Environment indicator
        env_color = {
            "production": "🟢",
            "staging": "🟡",
            "development": "🔵"
        }.get(config.ENVIRONMENT, "⚪")
        st.caption(f"{env_color} Environment: **{config.ENVIRONMENT}**")
        
        # Key metrics row
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Avg Query Time",
                f"{stats['avg_query_time_ms']:.0f}ms",
                help="Average database query duration"
            )
        with col2:
            cache_delta = None
            if stats['cache_hit_rate_pct'] > 80:
                cache_delta = "good"
            elif stats['cache_hit_rate_pct'] < 50 and stats['cache_hits'] + stats['cache_misses'] > 10:
                cache_delta = "low"
            st.metric(
                "Cache Hit Rate",
                f"{stats['cache_hit_rate_pct']:.0f}%",
                delta=cache_delta,
                delta_color="normal" if cache_delta == "good" else "inverse"
            )
        with col3:
            st.metric(
                "Total Queries",
                f"{stats['total_queries']:,}",
                help="Queries since app start"
            )
        with col4:
            error_delta = f"+{stats['error_count']}" if stats['error_count'] > 0 else None
            st.metric(
                "Errors",
                stats['error_count'],
                delta=error_delta,
                delta_color="inverse"
            )
        
        # Secondary metrics
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "P95 Query Time",
                f"{stats['p95_query_time_ms']:.0f}ms",
                help="95th percentile query duration"
            )
        with col2:
            st.metric(
                "Query Success Rate",
                f"{stats['query_success_rate_pct']:.1f}%"
            )
        with col3:
            st.metric(
                "Uptime",
                f"{stats['uptime_hours']:.1f}h"
            )
        
        # Recent errors
        if stats['recent_errors']:
            st.markdown("### ⚠️ Recent Errors")
            for err in stats['recent_errors'][-5:]:
                timestamp = err['timestamp'][:19].replace('T', ' ')
                st.error(f"**{timestamp}** [{err['type']}]: {err['message']}")
        
        # Materialized Views Status
        st.markdown("### 📊 Materialized Views")
        
        view_status = views_manager.get_all_status()
        
        # Create status table
        status_data = []
        for view_name in MaterializedViewsManager.VIEW_DEFINITIONS:
            info = view_status.get(view_name, {})
            last_refresh = info.get('last_refresh')
            if last_refresh:
                # Format as relative time
                from datetime import UTC, datetime
                try:
                    refresh_dt = datetime.fromisoformat(last_refresh)
                    age_mins = (datetime.now(UTC) - refresh_dt).total_seconds() / 60
                    if age_mins < 60:
                        age_str = f"{age_mins:.0f}m ago"
                    else:
                        age_str = f"{age_mins/60:.1f}h ago"
                except (ValueError, TypeError):
                    age_str = last_refresh[:16]
            else:
                age_str = "Never"
            
            status_icon = "✅" if info.get('status') == 'success' else "⚠️"
            
            status_data.append({
                "View": view_name.replace("mv_", ""),
                "Last Refresh": age_str,
                "Rows": info.get('row_count', 0),
                "Status": status_icon
            })
        
        if status_data:
            st.dataframe(
                status_data,
                use_container_width=True,
                hide_index=True
            )
        
        # Refresh button
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("🔄 Refresh All Views", type="primary"):
                with st.spinner("Refreshing materialized views..."):
                    results = views_manager.refresh_all()
                    success_count = sum(1 for v in results.values() if v)
                    total_count = len(results)
                    
                    if success_count == total_count:
                        st.success(f"All {total_count} views refreshed successfully!")
                    else:
                        st.warning(f"Refreshed {success_count}/{total_count} views. Check logs for errors.")
                    st.rerun()
        
        with col2:
            # Feature flags status
            flags = []
            if config.use_cached_views:
                flags.append("✓ Cached Views")
            if config.enable_background_jobs:
                flags.append("✓ Background Jobs")
            if config.enable_observability:
                flags.append("✓ Observability")
            
            if flags:
                st.caption("Feature Flags: " + " | ".join(flags))


def render_system_health_page():
    """Render a full system health page (for dedicated monitoring)."""
    st.title("🔧 System Health")
    st.markdown("Detailed system metrics and diagnostics.")
    
    render_system_health_widget()
    
    # Additional detailed sections could go here
    # e.g., query logs, error details, etc.
