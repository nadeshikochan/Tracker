# webui.py - v2.1 Fix
# Fixed: CSV parsing errors, datetime handling, encoding issues

import streamlit as st
import pandas as pd
import os
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
import common
import time
import math
import json
import io

# ==========================================
# 1. Page Config
# ==========================================
st.set_page_config(
    page_title="AI Time Tracker Dashboard",
    layout="wide",
    page_icon="⏱️",
    initial_sidebar_state="expanded"
)

# Custom styles
st.markdown("""
<style>
    .stApp { max-width: 100%; }
    
    /* Metric cards */
    div[data-testid="stMetric"] { 
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460; 
        padding: 15px; 
        border-radius: 10px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    div[data-testid="stMetricLabel"] {
        color: #a0a0a0 !important;
        font-size: 0.9rem;
    }
    
    div[data-testid="stMetricValue"] {
        color: #e94560 !important;
        font-size: 1.8rem;
        font-weight: bold;
    }
    
    .block-container { padding-top: 1rem; }
    
    /* Progress container */
    .goal-progress {
        background: #1a1a2e;
        border-radius: 8px;
        padding: 10px;
        margin: 5px 0;
    }
    
    .goal-label {
        color: #a0a0a0;
        font-size: 0.85rem;
    }
    
    /* Tab styles */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: #1a1a2e;
        border-radius: 8px;
        padding: 10px 20px;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 2. Data Processing Functions (FIXED)
# ==========================================
def clean_csv_line(line):
    """Clean and fix CSV line with wrong field count"""
    parts = line.strip().split(',')
    if len(parts) < 4:
        return None
    elif len(parts) == 4:
        return parts
    else:
        # More than 4 fields - merge extra parts into the last field (task detail)
        return [parts[0], parts[1], parts[2], ','.join(parts[3:])]


def process_single_file(file_path, date_str):
    """Read single CSV with robust error handling"""
    try:
        # First try: standard pandas read
        try:
            df = pd.read_csv(file_path, encoding='utf-8-sig', on_bad_lines='skip')
        except:
            try:
                df = pd.read_csv(file_path, encoding='utf-8', on_bad_lines='skip')
            except:
                # Manual parsing as fallback
                df = manual_parse_csv(file_path)
        
        if df is None or df.empty:
            return None
        
        # Normalize column names
        expected_cols = ['开始时间', '结束时间', '任务分类', '任务详情']
        if len(df.columns) >= 4:
            df.columns = expected_cols[:len(df.columns)]
        else:
            return None
        
        df['日期'] = date_str
        base_date = datetime.strptime(date_str, "%Y-%m-%d")

        def make_dt(t_str):
            if pd.isna(t_str):
                return None
            try:
                t_str = str(t_str).strip()
                # Try multiple formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%H:%M:%S', '%H:%M', '%Y/%m/%d %H:%M:%S']:
                    try:
                        if len(t_str) > 10:
                            return pd.to_datetime(t_str)
                        t = datetime.strptime(t_str, fmt).time()
                        return datetime.combine(base_date, t)
                    except:
                        continue
                # Last resort: try pandas auto-parsing
                try:
                    parsed = pd.to_datetime(t_str)
                    if parsed.year == 1900:  # Only time was parsed
                        return datetime.combine(base_date, parsed.time())
                    return parsed
                except:
                    pass
                return None
            except:
                return None

        df['Start_DT'] = df['开始时间'].apply(make_dt)
        df['End_DT'] = df['结束时间'].apply(make_dt)
        
        # Drop rows with invalid datetime
        df = df.dropna(subset=['Start_DT', 'End_DT'])
        
        if df.empty:
            return None
        
        # Calculate duration safely
        try:
            df['Duration_Min'] = (df['End_DT'] - df['Start_DT']).apply(
                lambda x: x.total_seconds() / 60 if pd.notna(x) else 0
            )
        except Exception:
            df['Duration_Min'] = 0
        
        df['Duration_Min'] = df['Duration_Min'].apply(lambda x: max(float(x), 0) if pd.notna(x) else 0)

        return df
    except Exception as e:
        st.error(f"File error {file_path}: {e}")
        return None


def manual_parse_csv(file_path):
    """Manually parse CSV file when pandas fails"""
    try:
        rows = []
        encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']
        
        content = None
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.readlines()
                break
            except:
                continue
        
        if not content:
            return None
        
        # Skip header
        for line in content[1:]:
            cleaned = clean_csv_line(line)
            if cleaned and len(cleaned) >= 4:
                rows.append(cleaned)
        
        if not rows:
            return None
        
        df = pd.DataFrame(rows, columns=['开始时间', '结束时间', '任务分类', '任务详情'])
        return df
    except:
        return None


def load_data_by_range(start_date, end_date):
    """Load data from date range"""
    dfs = []
    current = start_date
    while current <= end_date:
        d_str = current.strftime("%Y-%m-%d")
        f_path = os.path.join(common.LOG_DIR, f"{d_str}.csv")
        if os.path.exists(f_path):
            df = process_single_file(f_path, d_str)
            if df is not None and not df.empty:
                dfs.append(df)
        current += timedelta(days=1)

    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame()


def calculate_goal_progress(df, goals):
    """Calculate goal completion progress"""
    if df.empty or not goals.get("enabled"):
        return {}
    
    targets = goals.get("targets", {})
    limits = goals.get("limits", [])
    
    category_minutes = df.groupby('任务分类')['Duration_Min'].sum().to_dict()
    
    progress = {}
    for category, target in targets.items():
        actual = category_minutes.get(category, 0)
        is_limit = category in limits
        
        if is_limit:
            # Limit type: actual < target = 100%, over = decrease
            pct = max(0, 100 - (actual - target) / target * 100) if actual > target else 100
        else:
            # Goal type: actual / target
            pct = min(100, actual / target * 100) if target > 0 else 100
        
        progress[category] = {
            "actual": actual,
            "target": target,
            "percentage": pct,
            "is_limit": is_limit,
            "status": "OK" if pct >= 100 else "In Progress"
        }
    
    return progress


def get_weekly_summary(end_date):
    """Get weekly report data"""
    start_date = end_date - timedelta(days=6)
    df = load_data_by_range(start_date, end_date)
    
    if df.empty:
        return None, None
    
    # Daily totals
    daily_total = df.groupby('日期')['Duration_Min'].sum().reset_index()
    daily_total.columns = ['日期', '总时长']
    
    # Category summary
    category_summary = df.groupby('任务分类')['Duration_Min'].sum().reset_index()
    category_summary.columns = ['分类', '总时长(分钟)']
    category_summary['总时长(小时)'] = category_summary['总时长(分钟)'] / 60
    
    return daily_total, category_summary


# ==========================================
# 3. Sidebar
# ==========================================
st.sidebar.title("🎛️ Control Panel")

# Refresh button
if st.sidebar.button("🔄 Refresh Data", type="primary", use_container_width=True):
    st.rerun()

st.sidebar.divider()

# Date selection
today = date.today()
view_mode = st.sidebar.radio("📅 View Mode", ["Single Day", "Date Range", "This Week"], horizontal=True)

if view_mode == "Single Day":
    selected_date = st.sidebar.date_input("Select Date", value=today, max_value=today)
    start_date = end_date = selected_date
elif view_mode == "Date Range":
    date_range = st.sidebar.date_input(
        "Select Range",
        value=(today - timedelta(days=7), today),
        max_value=today
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = today
else:  # This Week
    start_date = today - timedelta(days=today.weekday())
    end_date = today

st.sidebar.caption(f"📆 {start_date} to {end_date}")

# Load data
df = load_data_by_range(start_date, end_date)

# Category filter
if not df.empty and '任务分类' in df.columns:
    st.sidebar.divider()
    all_categories = sorted(df['任务分类'].unique())
    selected_categories = st.sidebar.multiselect(
        "🏷️ Filter Categories",
        all_categories,
        default=all_categories
    )
    filtered_df = df[df['任务分类'].isin(selected_categories)]
else:
    filtered_df = df


# ==========================================
# 4. Main Content
# ==========================================
if df.empty:
    st.warning("📭 No data records in selected date range")
    
    # Show system log
    with st.expander("📟 System Log", expanded=True):
        if os.path.exists(common.RUNTIME_LOG_PATH):
            try:
                with open(common.RUNTIME_LOG_PATH, "r", encoding="utf-8", errors='ignore') as f:
                    lines = f.readlines()[-30:]
                st.code("".join(lines), language="text")
            except:
                st.info("Cannot read log file")
        else:
            st.info("No log file yet")
    st.stop()

# Title
days_count = (end_date - start_date).days + 1
title_suffix = f"({start_date})" if days_count == 1 else f"({start_date} ~ {end_date})"
st.title(f"📊 Time Tracking Report {title_suffix}")

# ==========================================
# 5. Core Metrics
# ==========================================
total_minutes = filtered_df['Duration_Min'].sum() if not filtered_df.empty else 0
total_hours = total_minutes / 60
total_sessions = len(filtered_df)
avg_session = total_minutes / max(total_sessions, 1)
total_days = days_count

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Time", f"{total_hours:.1f}h")
with col2:
    st.metric("Days", f"{total_days}")
with col3:
    st.metric("Sessions", f"{total_sessions}")
with col4:
    st.metric("Avg Duration", f"{avg_session:.0f}min")

st.divider()

# ==========================================
# 6. Tabs
# ==========================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Overview", "🗓️ Timeline", "🎯 Goals", "📝 Details", "📟 System Log"
])

# --- Tab 1: Overview ---
with tab1:
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.subheader("📊 Category Distribution")
        if not filtered_df.empty and '任务分类' in filtered_df.columns:
            category_time = filtered_df.groupby('任务分类')['Duration_Min'].sum().reset_index()
            category_time.columns = ['Category', 'Minutes']
            category_time['Hours'] = category_time['Minutes'] / 60
            
            fig_pie = px.pie(
                category_time,
                names='Category',
                values='Minutes',
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set2
            )
            fig_pie.update_layout(
                legend=dict(orientation="h", yanchor="bottom", y=-0.3),
                margin=dict(t=20, b=20, l=20, r=20)
            )
            st.plotly_chart(fig_pie, use_container_width=True)
    
    with chart_col2:
        st.subheader("📈 Category Ranking")
        if not filtered_df.empty:
            category_time_sorted = category_time.sort_values('Minutes', ascending=True)
            
            fig_bar = px.bar(
                category_time_sorted,
                x='Minutes',
                y='Category',
                orientation='h',
                color='Category',
                color_discrete_sequence=px.colors.qualitative.Set2,
                text=category_time_sorted['Hours'].apply(lambda x: f'{x:.1f}h')
            )
            fig_bar.update_layout(
                showlegend=False,
                margin=dict(t=20, b=20, l=20, r=20),
                xaxis_title="Minutes",
                yaxis_title=""
            )
            fig_bar.update_traces(textposition='outside')
            st.plotly_chart(fig_bar, use_container_width=True)
    
    # Heatmap for multi-day view
    if total_days > 1 and not filtered_df.empty:
        st.subheader("🔥 Activity Heatmap")
        
        try:
            # Create hour column safely
            filtered_df_copy = filtered_df.copy()
            filtered_df_copy['Hour'] = filtered_df_copy['Start_DT'].apply(
                lambda x: x.hour if pd.notna(x) else 0
            )
            
            heatmap_data = filtered_df_copy.groupby(['日期', 'Hour'])['Duration_Min'].sum().reset_index()
            heatmap_pivot = heatmap_data.pivot(index='Hour', columns='日期', values='Duration_Min').fillna(0)
            
            fig_heatmap = px.imshow(
                heatmap_pivot,
                labels=dict(x="Date", y="Hour", color="Minutes"),
                aspect="auto",
                color_continuous_scale="Viridis"
            )
            fig_heatmap.update_layout(
                margin=dict(t=20, b=20, l=20, r=20)
            )
            st.plotly_chart(fig_heatmap, use_container_width=True)
        except Exception as e:
            st.warning(f"Cannot generate heatmap: {e}")


# --- Tab 2: Timeline ---
with tab2:
    st.subheader("🗓️ Activity Timeline")
    st.caption("💡 Scroll to zoom | Drag to pan | Double-click to reset")
    
    if not filtered_df.empty:
        try:
            timeline_df = filtered_df.sort_values("Start_DT")
            y_categories = sorted(filtered_df['任务分类'].unique())
            
            # Alternating background
            shapes = []
            for i, cat in enumerate(y_categories):
                if i % 2 == 0:
                    shapes.append(dict(
                        type="rect", xref="paper", yref="y",
                        x0=0, x1=1, y0=i-0.5, y1=i+0.5,
                        fillcolor="rgba(255,255,255,0.05)",
                        layer="below", line_width=0
                    ))
            
            # Date format based on range
            tick_format = "%m-%d %H:%M" if total_days > 1 else "%H:%M"
            
            fig_timeline = px.timeline(
                timeline_df,
                x_start="Start_DT",
                x_end="End_DT",
                y="任务分类",
                color="任务分类",
                hover_data=["日期", "任务详情", "Duration_Min"],
                height=max(400, len(y_categories) * 60),
                category_orders={"任务分类": y_categories},
                color_discrete_sequence=px.colors.qualitative.Set2
            )
            
            fig_timeline.update_layout(
                xaxis=dict(
                    title="",
                    tickformat=tick_format,
                    showgrid=True,
                    gridcolor='rgba(128,128,128,0.3)'
                ),
                yaxis=dict(
                    autorange="reversed",
                    fixedrange=True,
                    title="",
                    showgrid=False
                ),
                legend=dict(orientation="h", y=1.1),
                margin=dict(l=10, r=10, t=10, b=10),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                bargap=0.3,
                shapes=shapes,
                dragmode="pan"
            )
            
            st.plotly_chart(
                fig_timeline,
                use_container_width=True,
                config={'scrollZoom': True, 'displayModeBar': True}
            )
        except Exception as e:
            st.error(f"Cannot render timeline: {e}")


# --- Tab 3: Goals ---
with tab3:
    st.subheader("🎯 Daily Goal Tracking")
    
    goals = common.load_goals()
    
    # Goal settings
    with st.expander("⚙️ Configure Goals", expanded=not goals.get("enabled", False)):
        goals_enabled = st.toggle("Enable Goal Tracking", value=goals.get("enabled", False))
        
        st.write("**Set target duration for each category (minutes)**")
        st.caption("💡 Entertainment/Social are upper limits, others are lower limits")
        
        targets = goals.get("targets", {})
        new_targets = {}
        
        cols = st.columns(4)
        default_categories = ["开发", "学习", "办公", "娱乐", "社交", "AI", "知识库"]
        
        for i, cat in enumerate(default_categories):
            with cols[i % 4]:
                new_targets[cat] = st.number_input(
                    f"{cat}",
                    min_value=0,
                    max_value=1440,
                    value=targets.get(cat, 60 if cat in ["娱乐", "社交"] else 120),
                    step=15,
                    key=f"goal_{cat}"
                )
        
        if st.button("💾 Save Goal Settings"):
            goals["enabled"] = goals_enabled
            goals["targets"] = new_targets
            goals["limits"] = ["娱乐", "社交"]
            if common.save_goals(goals):
                st.success("✅ Goals saved")
                st.rerun()
    
    # Progress display
    if goals.get("enabled") and total_days == 1:
        st.divider()
        progress = calculate_goal_progress(filtered_df, goals)
        
        if progress:
            cols = st.columns(len(progress))
            for i, (cat, data) in enumerate(progress.items()):
                with cols[i]:
                    status_icon = "✅" if data["percentage"] >= 100 else "🔄"
                    if data["is_limit"]:
                        status_icon = "✅" if data["actual"] <= data["target"] else "⚠️"
                    
                    st.markdown(f"**{status_icon} {cat}**")
                    
                    st.progress(min(data["percentage"] / 100, 1.0))
                    st.caption(f"{data['actual']:.0f} / {data['target']} min")
    elif goals.get("enabled"):
        st.info("📊 Goal progress details shown in single-day mode")


# --- Tab 4: Details ---
with tab4:
    st.subheader("📝 Data Details & Correction")
    
    # Export functions
    export_col1, export_col2, export_col3 = st.columns([2, 2, 6])
    with export_col1:
        if not filtered_df.empty:
            csv_data = filtered_df[['日期', '开始时间', '结束时间', '任务分类', '任务详情']].to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                "📥 Export CSV",
                data=csv_data,
                file_name=f"time_report_{start_date}_{end_date}.csv",
                mime="text/csv"
            )
    
    with export_col2:
        if not filtered_df.empty:
            # Simple stats report
            report = f"""# Time Tracking Report
## {start_date} ~ {end_date}

### Overview
- Total Duration: {total_hours:.1f} hours
- Days Covered: {total_days}
- Sessions: {total_sessions}
- Avg Duration: {avg_session:.0f} minutes

### Category Stats
"""
            for cat, mins in filtered_df.groupby('任务分类')['Duration_Min'].sum().items():
                report += f"- {cat}: {mins/60:.1f} hours\n"
            
            st.download_button(
                "📄 Export Report",
                data=report,
                file_name=f"time_report_{start_date}_{end_date}.md",
                mime="text/markdown"
            )
    
    st.divider()
    
    # Data editor
    if not filtered_df.empty:
        df_to_edit = filtered_df[['日期', '开始时间', '结束时间', '任务分类', '任务详情']].copy()
        
        edited_df = st.data_editor(
            df_to_edit,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "日期": st.column_config.TextColumn(disabled=True, width="small"),
                "开始时间": st.column_config.TextColumn(help="HH:MM:SS", width="small"),
                "结束时间": st.column_config.TextColumn(help="HH:MM:SS", width="small"),
                "任务分类": st.column_config.SelectboxColumn(
                    options=["开发", "AI", "知识库", "学习", "办公", "社交", "娱乐", "系统", "休息"],
                    width="small"
                ),
                "任务详情": st.column_config.TextColumn(width="large")
            }
        )
        
        if st.button("💾 Save Changes", type="primary"):
            try:
                grouped = edited_df.groupby('日期')
                saved_count = 0
                for date_key, group_data in grouped:
                    save_df = group_data[['开始时间', '结束时间', '任务分类', '任务详情']]
                    file_path = os.path.join(common.LOG_DIR, f"{date_key}.csv")
                    save_df.to_csv(file_path, index=False, encoding="utf-8-sig")
                    saved_count += 1
                st.success(f"✅ Saved {saved_count} file(s)")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"❌ Save failed: {e}")
    else:
        st.info("No data to edit")


# --- Tab 5: System Log ---
with tab5:
    st.subheader("📟 System Runtime Log")
    
    log_col1, log_col2 = st.columns([3, 1])
    with log_col2:
        if st.button("🔄 Refresh Log"):
            st.rerun()
    
    if 'log_page' not in st.session_state:
        st.session_state.log_page = 0
    
    if os.path.exists(common.RUNTIME_LOG_PATH):
        try:
            with open(common.RUNTIME_LOG_PATH, "r", encoding="utf-8", errors='ignore') as f:
                lines = f.readlines()
            
            lines.reverse()
            PAGE_SIZE = 50
            total_pages = math.ceil(len(lines) / PAGE_SIZE)
            
            if st.session_state.log_page >= total_pages:
                st.session_state.log_page = 0
            
            # Pagination controls
            nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
            with nav_col1:
                if st.button("⬅️ Prev") and st.session_state.log_page > 0:
                    st.session_state.log_page -= 1
                    st.rerun()
            with nav_col2:
                st.markdown(f"<center>Page {st.session_state.log_page + 1} / {max(1, total_pages)} ({len(lines)} total)</center>", unsafe_allow_html=True)
            with nav_col3:
                if st.button("Next ➡️") and st.session_state.log_page < total_pages - 1:
                    st.session_state.log_page += 1
                    st.rerun()
            
            # Display log
            start_idx = st.session_state.log_page * PAGE_SIZE
            end_idx = start_idx + PAGE_SIZE
            page_lines = lines[start_idx:end_idx]
            
            if page_lines:
                st.code("".join(page_lines), language="text")
            else:
                st.info("No log entries")
        except Exception as e:
            st.error(f"Failed to read log: {e}")
    else:
        st.info("No log file yet")


# ==========================================
# 7. Footer
# ==========================================
st.divider()
st.caption(f"🕐 Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | AI Time Tracker v2.1")
