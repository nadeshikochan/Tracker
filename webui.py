# webui.py - v3.0
# 保留原样式，去掉日志标签页

import streamlit as st
import pandas as pd
import os
import plotly.express as px
from datetime import datetime, date, timedelta
import common
import time
import csv

# ==========================================
# 【修复】Streamlit 性能优化配置
# ==========================================
if 'initialized' not in st.session_state:
    st.session_state.initialized = True

# ==========================================
# 1. 页面配置
# ==========================================
st.set_page_config(
    page_title="AI 时间追踪仪表盘",
    layout="wide",
    page_icon="⏱️",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    div[data-testid="stMetric"] { 
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460; 
        padding: 15px; 
        border-radius: 10px; 
    }
    div[data-testid="stMetricValue"] { color: #e94560 !important; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 2. 数据处理函数（带缓存）
# ==========================================
@st.cache_data(ttl=30)
def load_csv_file(file_path, date_str):
    """读取单个CSV文件（带缓存）"""
    try:
        df = None
        for encoding in ['utf-8-sig', 'utf-8', 'gbk']:
            try:
                df = pd.read_csv(file_path, encoding=encoding, on_bad_lines='skip')
                break
            except:
                continue
        
        if df is None or df.empty:
            return None
        
        if len(df.columns) >= 4:
            df.columns = ['开始时间', '结束时间', '任务分类', '任务详情'][:len(df.columns)]
        else:
            return None
        
        return df
    except:
        return None


def process_dataframe(df, date_str):
    """处理DataFrame，添加时间列"""
    if df is None or df.empty:
        return None
    
    df = df.copy()
    df['日期'] = date_str
    base_date = datetime.strptime(date_str, "%Y-%m-%d")
    
    def parse_time(t_str):
        if pd.isna(t_str):
            return None
        t_str = str(t_str).strip()
        for fmt in ['%Y-%m-%d %H:%M:%S', '%H:%M:%S', '%H:%M']:
            try:
                if len(t_str) > 10:
                    return pd.to_datetime(t_str)
                t = datetime.strptime(t_str, fmt).time()
                return datetime.combine(base_date, t)
            except:
                continue
        return None
    
    df['Start_DT'] = df['开始时间'].apply(parse_time)
    df['End_DT'] = df['结束时间'].apply(parse_time)
    df = df.dropna(subset=['Start_DT', 'End_DT'])
    
    if df.empty:
        return None
    
    df['Duration_Min'] = (df['End_DT'] - df['Start_DT']).apply(
        lambda x: max(x.total_seconds() / 60, 0) if pd.notna(x) else 0
    )
    
    return df


def load_data_by_range(start_date, end_date):
    """加载日期范围内的数据"""
    dfs = []
    current = start_date
    while current <= end_date:
        d_str = current.strftime("%Y-%m-%d")
        f_path = os.path.join(common.LOG_DIR, f"{d_str}.csv")
        if os.path.exists(f_path):
            raw_df = load_csv_file(f_path, d_str)
            df = process_dataframe(raw_df, d_str)
            if df is not None:
                dfs.append(df)
        current += timedelta(days=1)
    
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame()


def calculate_goal_progress(df, goals):
    """计算目标完成进度"""
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
            pct = max(0, 100 - (actual - target) / target * 100) if actual > target else 100
        else:
            pct = min(100, actual / target * 100) if target > 0 else 100
        
        progress[category] = {
            "actual": actual,
            "target": target,
            "percentage": pct,
            "is_limit": is_limit
        }
    
    return progress


# ==========================================
# 3. 侧边栏
# ==========================================
st.sidebar.title("🎛️ 控制面板")

if st.sidebar.button("🔄 刷新数据", type="primary", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.divider()

today = date.today()
view_mode = st.sidebar.radio("📅 查看模式", ["单日", "日期范围", "本周"], horizontal=True)

if view_mode == "单日":
    selected_date = st.sidebar.date_input("选择日期", value=today, max_value=today)
    start_date = end_date = selected_date
elif view_mode == "日期范围":
    date_range = st.sidebar.date_input("选择范围", value=(today - timedelta(days=7), today), max_value=today)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = today
else:
    start_date = today - timedelta(days=today.weekday())
    end_date = today

st.sidebar.caption(f"📆 {start_date} 至 {end_date}")

# 加载数据
df = load_data_by_range(start_date, end_date)

# 分类过滤
if not df.empty and '任务分类' in df.columns:
    st.sidebar.divider()
    all_categories = sorted(df['任务分类'].unique())
    selected_categories = st.sidebar.multiselect("🏷️ 筛选分类", all_categories, default=all_categories)
    filtered_df = df[df['任务分类'].isin(selected_categories)]
else:
    filtered_df = df


# ==========================================
# 4. 主内容区
# ==========================================
if df.empty:
    st.warning("📭 选定日期范围内没有数据记录")
    st.info("请确保 Tracker 正在运行，并等待记录一些活动")
    st.stop()

days_count = (end_date - start_date).days + 1
title_suffix = f"({start_date})" if days_count == 1 else f"({start_date} ~ {end_date})"
st.title(f"📊 时间追踪报告 {title_suffix}")

# 核心指标
total_minutes = filtered_df['Duration_Min'].sum() if not filtered_df.empty else 0
total_hours = total_minutes / 60
total_sessions = len(filtered_df)
avg_session = total_minutes / max(total_sessions, 1)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("总记录时长", f"{total_hours:.1f}小时")
with col2:
    st.metric("覆盖天数", f"{days_count}天")
with col3:
    st.metric("活动条数", f"{total_sessions}条")
with col4:
    st.metric("平均时长", f"{avg_session:.0f}分钟")

st.divider()

# ==========================================
# 5. 标签页（去掉日志标签页）
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["📊 总览", "🗓️ 时间轴", "🎯 目标追踪", "📝 数据明细"])

with tab1:
    if not filtered_df.empty and '任务分类' in filtered_df.columns:
        chart_col1, chart_col2 = st.columns(2)
        
        category_time = filtered_df.groupby('任务分类')['Duration_Min'].sum().reset_index()
        category_time.columns = ['分类', '分钟']
        category_time['小时'] = category_time['分钟'] / 60
        
        with chart_col1:
            st.subheader("📊 分类占比")
            fig_pie = px.pie(category_time, names='分类', values='分钟', hole=0.4,
                           color_discrete_sequence=px.colors.qualitative.Set2)
            fig_pie.update_layout(legend=dict(orientation="h", y=-0.2), margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with chart_col2:
            st.subheader("📈 分类排行")
            category_time_sorted = category_time.sort_values('分钟', ascending=True)
            fig_bar = px.bar(category_time_sorted, x='分钟', y='分类', orientation='h', color='分类',
                           color_discrete_sequence=px.colors.qualitative.Set2,
                           text=category_time_sorted['小时'].apply(lambda x: f'{x:.1f}h'))
            fig_bar.update_layout(showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
            fig_bar.update_traces(textposition='outside')
            st.plotly_chart(fig_bar, use_container_width=True)

with tab2:
    st.subheader("🗓️ 活动时间轴")
    st.caption("💡 滚轮缩放 | 拖动平移 | 双击重置")
    
    if not filtered_df.empty:
        try:
            timeline_df = filtered_df.sort_values("Start_DT")
            y_categories = sorted(filtered_df['任务分类'].unique())
            tick_format = "%m-%d %H:%M" if days_count > 1 else "%H:%M"
            
            fig_timeline = px.timeline(timeline_df, x_start="Start_DT", x_end="End_DT", y="任务分类",
                                      color="任务分类", hover_data=["日期", "任务详情", "Duration_Min"],
                                      height=max(400, len(y_categories) * 60),
                                      color_discrete_sequence=px.colors.qualitative.Set2)
            fig_timeline.update_layout(
                xaxis=dict(title="", tickformat=tick_format, showgrid=True, fixedrange=False),
                yaxis=dict(autorange="reversed", title="", fixedrange=True),
                legend=dict(orientation="h", y=1.1),
                margin=dict(l=10, r=10, t=10, b=10),
                dragmode="zoom"  # 或直接删掉
            )
            st.plotly_chart(
                fig_timeline,
                use_container_width=True,
                config={
                    'scrollZoom': True,  # ✅ 只能是 True / False
                    'displayModeBar': True
                }
            )
        except Exception as e:
            st.error(f"无法渲染时间轴: {e}")

with tab3:
    st.subheader("🎯 每日目标追踪")
    goals = common.load_goals()
    
    with st.expander("⚙️ 设置目标", expanded=not goals.get("enabled", False)):
        goals_enabled = st.toggle("启用目标追踪", value=goals.get("enabled", False))
        st.write("**设定各分类目标时长（分钟）**")
        st.caption("💡 娱乐/社交类为上限目标（不应超过），其他为下限目标（应达到）")
        
        targets = goals.get("targets", {})
        new_targets = {}
        cols = st.columns(4)
        for i, cat in enumerate(["开发", "学习", "办公", "娱乐", "社交", "AI", "知识库"]):
            with cols[i % 4]:
                new_targets[cat] = st.number_input(f"{cat}", min_value=0, max_value=1440,
                    value=targets.get(cat, 60 if cat in ["娱乐", "社交"] else 120), step=15, key=f"goal_{cat}")
        
        if st.button("💾 保存目标设置"):
            goals["enabled"] = goals_enabled
            goals["targets"] = new_targets
            goals["limits"] = ["娱乐", "社交"]
            if common.save_goals(goals):
                st.success("✅ 目标已保存")
                st.rerun()
    
    if goals.get("enabled") and days_count == 1:
        st.divider()
        progress = calculate_goal_progress(filtered_df, goals)
        if progress:
            cols = st.columns(len(progress))
            for i, (cat, data) in enumerate(progress.items()):
                with cols[i]:
                    icon = "✅" if data["percentage"] >= 100 else "🔄"
                    if data["is_limit"]:
                        icon = "✅" if data["actual"] <= data["target"] else "⚠️"
                    st.markdown(f"**{icon} {cat}**")
                    st.progress(min(data["percentage"] / 100, 1.0))
                    st.caption(f"{data['actual']:.0f} / {data['target']} 分钟")

with tab4:
    st.subheader("📝 数据明细与修正")
    
    if not filtered_df.empty:
        col1, col2, _ = st.columns([2, 2, 6])
        with col1:
            csv_data = filtered_df[['日期', '开始时间', '结束时间', '任务分类', '任务详情']].to_csv(index=False, encoding='utf-8-sig')
            st.download_button("📥 导出 CSV", data=csv_data, file_name=f"报告_{start_date}_{end_date}.csv", mime="text/csv")
        
        st.divider()
        
        df_to_edit = filtered_df[['日期', '开始时间', '结束时间', '任务分类', '任务详情']].copy()
        edited_df = st.data_editor(df_to_edit, num_rows="dynamic", use_container_width=True, hide_index=True,
            column_config={
                "日期": st.column_config.TextColumn(disabled=True, width="small"),
                "任务分类": st.column_config.SelectboxColumn(
                    options=["开发", "AI", "知识库", "学习", "办公", "社交", "娱乐", "系统", "休息"], width="small")
            })
        
        if st.button("💾 保存修改", type="primary"):
            try:
                for date_key, group_data in edited_df.groupby('日期'):
                    save_df = group_data[['开始时间', '结束时间', '任务分类', '任务详情']]
                    save_df.to_csv(os.path.join(common.LOG_DIR, f"{date_key}.csv"), index=False, encoding="utf-8-sig")
                st.cache_data.clear()
                st.success("✅ 保存成功")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"❌ 保存失败: {e}")
    else:
        st.info("暂无数据")

st.divider()
st.caption(f"🕐 最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | AI 时间追踪系统 v3.0")
