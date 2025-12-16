
# webui.py
import streamlit as st
import pandas as pd
import os
import plotly.express as px
from datetime import datetime, date, timedelta
import common
import time
import math

# ================= 1. 页面与样式配置 =================
st.set_page_config(page_title="AI 时间追踪仪表盘", layout="wide", page_icon="⏱️")

st.markdown("""
<style>
    .stApp { max-width: 100%; }

    /* 指标卡片：深色背景，适配黑夜模式 */
    div[data-testid="stMetric"] { 
        background-color: #1E1E1E; 
        border: 1px solid #333333; 
        padding: 10px; 
        border-radius: 8px; 
        color: #FFFFFF; 
    }

    div[data-testid="stMetricLabel"] {
        color: #A0A0A0 !important;
    }

    .block-container { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)


# ================= 2. 核心逻辑函数 =================
def process_single_file(file_path, date_str):
    """读取单个CSV并添加日期列"""
    try:
        df = pd.read_csv(file_path)
        if df.empty: return None

        df['日期'] = date_str
        base_date = datetime.strptime(date_str, "%Y-%m-%d")

        def make_dt(t_str):
            try:
                t_str = str(t_str).strip()
                if len(t_str) > 10:
                    return pd.to_datetime(t_str)
                t = datetime.strptime(t_str, "%H:%M:%S").time()
                return datetime.combine(base_date, t)
            except:
                return None

        df['Start_DT'] = df['开始时间'].apply(make_dt)
        df['End_DT'] = df['结束时间'].apply(make_dt)

        # 清洗
        df = df.dropna(subset=['Start_DT', 'End_DT'])

        # 计算时长
        df['Duration_Min'] = (df['End_DT'] - df['Start_DT']).dt.total_seconds() / 60
        df['Duration_Min'] = df['Duration_Min'].apply(lambda x: x if x > 0 else 0)

        return df
    except Exception as e:
        return None


def load_data_by_range(start_date, end_date):
    """加载指定日期范围内的所有数据"""
    all_files = common.get_all_csv_files()
    dfs = []

    current_date = start_date
    while current_date <= end_date:
        d_str = current_date.strftime("%Y-%m-%d")
        f_name = f"{d_str}.csv"
        f_path = os.path.join(common.LOG_DIR, f_name)

        if os.path.exists(f_path):
            df = process_single_file(f_path, d_str)
            if df is not None:
                dfs.append(df)

        current_date += timedelta(days=1)

    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame()


# ================= 3. 侧边栏与数据加载 =================
st.sidebar.title("🎛️ 控制台")

if st.sidebar.button("🔄 刷新数据", type="primary"):
    st.rerun()

# --- 日期选择器 ---
today = date.today()
date_range = st.sidebar.date_input(
    "📅 选择日期 (支持多天)",
    value=(today, today),
    max_value=today,
    format="YYYY-MM-DD"
)

start_date, end_date = today, today
if isinstance(date_range, tuple):
    if len(date_range) == 2:
        start_date, end_date = date_range
    elif len(date_range) == 1:
        start_date = end_date = date_range[0]
else:
    start_date = end_date = date_range

st.sidebar.caption(f"当前选中: {start_date} 至 {end_date}")

# 加载数据
df = load_data_by_range(start_date, end_date)

if df.empty:
    st.warning("📭 当前选择的日期范围内没有记录数据。")
    with st.expander("📟 系统控制台日志 (Runtime Log)", expanded=True):
        if os.path.exists(common.RUNTIME_LOG_PATH):
            with open(common.RUNTIME_LOG_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()[-50:]
                st.code("".join(lines), language="text")
    st.stop()

# 分类过滤器
if '任务分类' in df.columns:
    all_categories = list(df['任务分类'].unique())
    selected_categories = st.sidebar.multiselect("🏷️ 过滤分类", all_categories, default=all_categories)
    filtered_df = df[df['任务分类'].isin(selected_categories)]
else:
    filtered_df = df

# ================= 4. 仪表盘主体 =================
st.title(f"📊 活动报表 ({start_date} ~ {end_date})")

# --- 核心指标 ---
total_minutes = filtered_df['Duration_Min'].sum()
top_task = filtered_df.groupby('任务分类')['Duration_Min'].sum().idxmax() if not filtered_df.empty else "N/A"
avg_duration = filtered_df['Duration_Min'].mean()
total_days = filtered_df['日期'].nunique()

col1, col2, col3, col4 = st.columns(4)
col1.metric("⏱️ 总记录时长", f"{total_minutes / 60:.1f} 小时")
col2.metric("📅 覆盖天数", f"{total_days} 天")
col3.metric("🏆 最耗时分类", top_task)
col4.metric("🧠 平均专注片段", f"{avg_duration:.1f} 分钟")

st.divider()

# --- 统计图表区 ---
col_chart1, col_chart2 = st.columns([1, 1])

with col_chart1:
    st.subheader("⏳ 分类占比")
    cat_duration = filtered_df.groupby('任务分类')['Duration_Min'].sum().reset_index()
    fig_pie = px.pie(cat_duration, values='Duration_Min', names='任务分类', hole=0.4)
    fig_pie.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=350,
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig_pie, use_container_width=True)

with col_chart2:
    st.subheader("📈 趋势与排行")
    if total_days > 1:
        daily_trend = filtered_df.groupby(['日期', '任务分类'])['Duration_Min'].sum().reset_index()
        fig_bar = px.bar(daily_trend, x='日期', y='Duration_Min', color='任务分类',
                         title="每日时长分布", barmode='stack')
    else:
        fig_bar = px.bar(cat_duration.sort_values('Duration_Min', ascending=True),
                         x='Duration_Min', y='任务分类', orientation='h', text_auto='.0f',
                         color='任务分类', title="分类耗时排行")

    fig_bar.update_layout(
        margin=dict(t=30, b=10, l=10, r=10),
        height=350,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)'),
        yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)')
    )
    st.plotly_chart(fig_bar, use_container_width=True)

# --- 交互式时间轴 (终极优化版) ---
st.subheader("🗓️ 活动时间轴")
st.caption("💡 提示：**滚动鼠标滚轮**可缩放时间 | **拖动**平移时间轴 | **双击**重置视图")

if not filtered_df.empty:
    timeline_df = filtered_df.sort_values("Start_DT")

    # 1. 确定 Y 轴顺序 (确保交错背景能对齐)
    # 按总时长排序，让重要的在上面，或者 simple sorted()
    # 这里用 sorted() 保证稳定性
    y_categories = sorted(filtered_df['任务分类'].unique())

    # 2. 生成交错背景 (Zebra Striping)
    shapes = []
    for i, cat in enumerate(y_categories):
        # 给偶数行添加背景色
        if i % 2 == 0:
            shapes.append(dict(
                type="rect",
                xref="paper",  # x轴占满整个图表宽度
                yref="y",  # y轴对应数据坐标
                x0=0,
                x1=1,
                y0=i - 0.5,  # 类别索引从0开始，区间是 [i-0.5, i+0.5]
                y1=i + 0.5,
                fillcolor="rgba(255, 255, 255, 0.07)",  # 浅白色，在深色背景下显现为稍亮的条纹
                layer="below",  # 放在图层最底部
                line_width=0,
            ))

    fig_timeline = px.timeline(
        timeline_df,
        x_start="Start_DT",
        x_end="End_DT",
        y="任务分类",
        color="任务分类",
        hover_data=["日期", "任务详情", "Duration_Min"],
        height=500,
        # 3. 强制指定分类顺序，必须与 shapes 的索引逻辑一致！
        category_orders={"任务分类": y_categories}
    )

    # === 布局深度定制 ===
    fig_timeline.update_layout(
        xaxis=dict(
            title="",
            tickformat="%H:%M",  # 即使是多天，时间轴通常看具体时刻，如果跨度大 Plotly 会自动调整
            rangeslider=dict(visible=False),  # 隐藏底部滑块，使用滚轮缩放更直观
            type="date",
            side="bottom",
            # 垂直刻度线 (辅助时间对齐)
            showgrid=True,
            gridcolor='rgba(128, 128, 128, 0.3)',  # 稍微明显一点的竖线
            gridwidth=1,
        ),
        yaxis=dict(
            autorange="reversed",  # 让第一个分类显示在最上面
            fixedrange=True,  # 锁定Y轴，防止缩放错位
            title="",
            showgrid=False,  # 关闭默认网格，因为我们用了交错背景
            zeroline=False
        ),
        legend=dict(orientation="h", y=1.1, x=0),
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        bargap=0.3,  # 增加条形间距，让背景条纹更明显
        shapes=shapes,  # 应用交错背景
        dragmode="pan",  # 默认交互模式为平移
    )

    # 4. 开启滚轮缩放 (scrollZoom=True)
    config = {
        'scrollZoom': True,
        'displayModeBar': True,
        'modeBarButtonsToRemove': ['lasso2d', 'select2d']
    }

    st.plotly_chart(fig_timeline, use_container_width=True, config=config)

st.divider()

# --- 日志查看器 (倒序 + 分页) ---
with st.expander("📟 系统后台运行日志", expanded=False):
    st.caption(f"日志路径: {common.RUNTIME_LOG_PATH}")

    # 1. 初始化页码状态
    if 'log_page_index' not in st.session_state:
        st.session_state.log_page_index = 0

    if os.path.exists(common.RUNTIME_LOG_PATH):
        try:
            with open(common.RUNTIME_LOG_PATH, "r", encoding="utf-8", errors='ignore') as f:
                lines = f.readlines()

            # 【关键】倒序排列：最新的在最前面
            lines.reverse()

            # 分页计算
            PAGE_SIZE = 100
            total_lines = len(lines)
            total_pages = math.ceil(total_lines / PAGE_SIZE)

            # 防止页码越界 (例如日志被清空，但页码还停留在第5页)
            if st.session_state.log_page_index >= total_pages:
                st.session_state.log_page_index = 0

            # --- 顶部控制栏布局 ---
            c1, c2, c3, c4 = st.columns([1, 1, 2, 1])

            with c1:
                # 刷新按钮：点击后重置回第一页
                if st.button("🔄 刷新"):
                    st.session_state.log_page_index = 0
                    st.rerun()

            with c2:
                # 上一页按钮
                if st.session_state.log_page_index > 0:
                    if st.button("⬅️ 上一页"):
                        st.session_state.log_page_index -= 1
                        st.rerun()

            with c3:
                # 页码显示
                display_page = st.session_state.log_page_index + 1
                display_total = max(1, total_pages)
                st.markdown(
                    f"<div style='text-align: center; line-height: 2.3em; color: gray;'>"
                    f"第 {display_page} / {display_total} 页 (共 {total_lines} 条)"
                    f"</div>",
                    unsafe_allow_html=True
                )

            with c4:
                # 下一页按钮
                if st.session_state.log_page_index < total_pages - 1:
                    if st.button("下一页 ➡️"):
                        st.session_state.log_page_index += 1
                        st.rerun()

            # --- 内容切片与显示 ---
            start_idx = st.session_state.log_page_index * PAGE_SIZE
            end_idx = start_idx + PAGE_SIZE

            # 获取当前页日志
            page_content_lines = lines[start_idx:end_idx]

            if page_content_lines:
                st.code("".join(page_content_lines), language="text")
            else:
                st.info("当前暂无日志数据")

        except Exception as e:
            st.error(f"无法读取日志: {e}")
    else:
        st.info("暂无日志文件。")

st.divider()

# --- 数据修正区 ---
st.subheader("📝 数据明细与修正")
st.caption("修改后请点击保存。日期列不可修改。")

df_to_edit = filtered_df[['日期', '开始时间', '结束时间', '任务分类', '任务详情']].copy()

edited_df = st.data_editor(
    df_to_edit,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "日期": st.column_config.TextColumn(disabled=True),
        "开始时间": st.column_config.TextColumn(help="HH:MM:SS"),
        "结束时间": st.column_config.TextColumn(help="HH:MM:SS"),
    }
)

if st.button("💾 保存所有修改", type="primary"):
    try:
        grouped = edited_df.groupby('日期')
        saved_files = []
        for date_key, group_data in grouped:
            save_df = group_data[['开始时间', '结束时间', '任务分类', '任务详情']]
            file_path = os.path.join(common.LOG_DIR, f"{date_key}.csv")
            save_df.to_csv(file_path, index=False, encoding="utf-8-sig")
            saved_files.append(date_key)
        st.toast(f"✅ 成功保存 {len(saved_files)} 个文件的数据！", icon="🎉")
        time.sleep(1.5)
        st.rerun()
    except Exception as e:
        st.error(f"❌ 保存失败: {e}")

