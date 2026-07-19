import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "latest_jobs.csv"
UPDATE_PATH = BASE_DIR / "data" / "latest_update.json"
LOG_PATH = BASE_DIR / "logs" / f"{date.today().isoformat()}.log"

st.set_page_config(
    page_title="辽宁高校行政招聘信息库",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"] {background:#f5f7fa;}
[data-testid="stHeader"] {background:transparent;}
.hero {background:linear-gradient(115deg,#10233f,#1769aa);padding:25px 30px;border-radius:14px;color:white;margin-bottom:18px;box-shadow:0 9px 28px rgba(16,35,63,.14)}
.hero h1 {font-size:29px;margin:0 0 8px}.hero p{margin:0;color:#d8e8f5}
.notice {background:#edf6fb;border-left:4px solid #1769aa;padding:12px 15px;border-radius:7px;margin:10px 0 18px;color:#344054}
[data-testid="stMetric"] {background:white;border:1px solid #e5e9ef;padding:14px;border-radius:11px;box-shadow:0 4px 14px rgba(18,38,63,.04)}
[data-testid="stMetricValue"] {color:#1769aa;font-size:27px}
.section {font-size:19px;font-weight:700;color:#172033;margin:14px 0 8px}
.status-ok {display:inline-block;background:#e9f7f2;color:#14866d;border-radius:99px;padding:3px 9px;font-size:12px;font-weight:600}
.small-note {font-size:12px;color:#697586}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def load_data():
    frame = pd.read_csv(DATA_PATH, encoding="utf-8-sig")
    frame["post_date"] = pd.to_datetime(frame["post_date"], errors="coerce")
    frame["deadline"] = pd.to_datetime(frame["deadline"], errors="coerce")
    frame["first_seen_at"] = pd.to_datetime(frame["first_seen_at"], errors="coerce")
    frame["last_seen_at"] = pd.to_datetime(frame["last_seen_at"], errors="coerce")
    return frame


@st.cache_data(ttl=60)
def load_source_status():
    if not LOG_PATH.exists():
        return []
    statuses = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            statuses.append(json.loads(line))
    return statuses


if not DATA_PATH.exists():
    st.error("尚未找到 data/latest_jobs.csv，请先运行 python daily_update.py。")
    st.stop()

df = load_data()
if UPDATE_PATH.exists():
    update_info = json.loads(UPDATE_PATH.read_text(encoding="utf-8"))
    latest_text = update_info.get("last_update", "未知")
else:
    latest_check = df["last_seen_at"].max()
    latest_text = latest_check.strftime("%Y-%m-%d %H:%M") if pd.notna(latest_check) else "未知"

st.markdown(f"""
<div class="hero"><h1>辽宁大连·沈阳高校行政招聘信息库</h1>
<p>聚合高校及政府官方招聘公告 · 最近检查：{latest_text}</p></div>
<div class="notice">本平台为招聘信息聚合工具，公告内容、报名条件及时间以学校或政府官方页面为准。</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("筛选条件")
    keyword = st.text_input("关键词", placeholder="公告标题、岗位关键词")
    cities = st.multiselect("城市", sorted(df["city"].dropna().unique()))
    schools = st.multiselect("学校 / 平台", sorted(df["school"].dropna().unique()))
    years = st.multiselect("年份", sorted(df["year"].dropna().astype(int).unique(), reverse=True))
    categories = st.multiselect("岗位类别", sorted(df["job_category"].dropna().unique()))
    degrees = st.multiselect("学历要求", sorted(df["degree_requirement"].dropna().unique()))
    statuses = st.multiselect("状态", sorted(df["status"].dropna().unique()))
    fresh_only = st.checkbox("仅看应届生相关")
    party_only = st.checkbox("仅看党员要求")
    default_focus = st.checkbox("聚焦行政/辅导员/教辅", value=True)
    st.caption("取消聚焦可查看全部采集公告。")

view = df.copy()
if keyword:
    query = keyword.strip()
    search_columns = view[["title", "position_keywords", "summary"]].fillna("").agg(" ".join, axis=1)
    view = view[search_columns.str.contains(query, case=False, regex=False)]
if cities:
    view = view[view["city"].isin(cities)]
if schools:
    view = view[view["school"].isin(schools)]
if years:
    view = view[view["year"].isin(years)]
if categories:
    view = view[view["job_category"].isin(categories)]
if degrees:
    view = view[view["degree_requirement"].isin(degrees)]
if statuses:
    view = view[view["status"].isin(statuses)]
if fresh_only:
    view = view[view["fresh_graduate"] == "是"]
if party_only:
    view = view[view["political_requirement"] == "是"]
if default_focus:
    view = view[view["job_category"].isin(["行政管理", "辅导员", "组织员", "教辅/实验技术", "待人工复核"])]

view = view.sort_values(["post_date", "id"], ascending=[False, False])
today = pd.Timestamp(date.today())
week_start = today - pd.Timedelta(days=6)
new_week = int((view["post_date"] >= week_start).sum())
admin_count = int(view["job_category"].isin(["行政管理", "辅导员", "组织员"]).sum())
support_count = int((view["job_category"] == "教辅/实验技术").sum())
active_count = int((view["status"] == "有效").sum())

cols = st.columns(5)
cols[0].metric("筛选结果", len(view))
cols[1].metric("近 7 日公告", new_week)
cols[2].metric("行政及辅导员", admin_count)
cols[3].metric("教辅 / 实验技术", support_count)
cols[4].metric("有效记录", active_count)

main_tab, source_tab, review_tab = st.tabs(["招聘信息", "来源状态", "人工复核"])

with main_tab:
    st.markdown('<div class="section">招聘公告</div>', unsafe_allow_html=True)
    display = view.copy()
    display["发布日期"] = display["post_date"].dt.strftime("%Y-%m-%d").fillna("未标明")
    display["截止日期"] = display["deadline"].dt.strftime("%Y-%m-%d").fillna("未明确")
    display["公告标题"] = display["title"]
    display["城市"] = display["city"]
    display["学校 / 平台"] = display["school"]
    display["岗位类别"] = display["job_category"]
    display["学历"] = display["degree_requirement"]
    display["状态"] = display["status"]
    display["官方原文"] = display["detail_url"]
    display["附件"] = display["attachment_urls"].fillna("").apply(lambda value: value.split("|")[0] if value else "")
    st.dataframe(
        display[["发布日期", "城市", "学校 / 平台", "公告标题", "岗位类别", "学历", "截止日期", "状态", "官方原文", "附件"]],
        height=520,
    )
    export_frame = view.copy()
    for column in ("post_date", "deadline", "first_seen_at", "last_seen_at"):
        export_frame[column] = export_frame[column].astype(str).replace("NaT", "")
    st.download_button(
        "导出当前筛选结果 CSV",
        export_frame.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"辽宁高校招聘筛选结果_{date.today().isoformat()}.csv",
        mime="text/csv",
    )

with source_tab:
    source_status = load_source_status()
    if source_status:
        status_df = pd.DataFrame(source_status)
        source_names = df[["source_id", "school"]].drop_duplicates()
        status_df = status_df.merge(source_names, on="source_id", how="left")
        status_df = status_df.rename(columns={"school": "学校 / 平台", "status": "状态", "records": "本轮记录", "new": "新增", "updated": "修改", "error": "错误信息"})
        st.dataframe(status_df[["学校 / 平台", "状态", "本轮记录", "新增", "修改", "错误信息"]])
        success_count = sum(item["status"] == "成功" for item in source_status)
        st.markdown(f'<span class="status-ok">{success_count} / {len(source_status)} 来源运行成功</span>', unsafe_allow_html=True)
    else:
        st.info("今天尚无来源运行日志。")

with review_tab:
    review = df[df["job_category"] == "待人工复核"].copy()
    st.write(f"待人工确认是否属于行政、辅导员或教辅岗位：**{len(review)} 条**")
    review["发布日期"] = review["post_date"].dt.strftime("%Y-%m-%d").fillna("未标明")
    review["官方原文"] = review["detail_url"]
    st.dataframe(
        review[["发布日期", "city", "school", "title", "position_keywords", "官方原文"]].rename(columns={"city": "城市", "school": "学校 / 平台", "title": "公告标题", "position_keywords": "命中关键词"}),
    )

st.caption("数据来源：各高校、辽宁省教育厅及沈阳市人力资源和社会保障局官方页面。")
