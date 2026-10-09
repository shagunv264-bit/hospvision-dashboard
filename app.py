"""
Real-Time HospVision Dashboard
Tracks bed occupancy, ICU availability, and critical equipment
across multiple hospital departments / branches.
"""

import time
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

import db_utils
from db_setup import create_schema, seed as seed_db

_IST = ZoneInfo("Asia/Kolkata")


def _now_ist() -> datetime:
    """Return current datetime in Asia/Kolkata timezone."""
    return datetime.now(_IST)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HospVision",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Main background */
    .stApp { background-color: #0f1117; color: #e8eaf0; }

    /* Sidebar */
    [data-testid="stSidebar"] { background-color: #1a1d27; }
    [data-testid="stSidebar"] .stMarkdown { color: #c5cae9; }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: #1e2130;
        border: 1px solid #2a2f45;
        border-radius: 10px;
        padding: 14px 18px;
    }
    [data-testid="stMetricLabel"]  { color: #8b93b5 !important; font-size: 0.78rem; letter-spacing: 0.05em; text-transform: uppercase; }
    [data-testid="stMetricValue"]  { color: #e8eaf0 !important; font-size: 1.6rem; font-weight: 700; }
    [data-testid="stMetricDelta"]  { font-size: 0.82rem; }

    /* Section headers */
    .section-header {
        font-size: 1rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #7c86c4;
        margin: 0.8rem 0 0.4rem 0;
        border-bottom: 1px solid #2a2f45;
        padding-bottom: 4px;
    }

    /* Status pill badges */
    .pill-ok       { background:#14432a; color:#4ade80; padding:2px 10px; border-radius:12px; font-size:0.78rem; font-weight:600; }
    .pill-warn     { background:#3f2d05; color:#fbbf24; padding:2px 10px; border-radius:12px; font-size:0.78rem; font-weight:600; }
    .pill-critical { background:#3f0f0f; color:#f87171; padding:2px 10px; border-radius:12px; font-size:0.78rem; font-weight:600; }

    /* Alert banner */
    .alert-banner {
        background: #3f0f0f;
        border-left: 4px solid #ef4444;
        color: #fca5a5;
        padding: 10px 14px;
        border-radius: 6px;
        margin-bottom: 10px;
        font-size: 0.88rem;
    }
    .info-banner {
        background: #0c2240;
        border-left: 4px solid #3b82f6;
        color: #93c5fd;
        padding: 10px 14px;
        border-radius: 6px;
        margin-bottom: 10px;
        font-size: 0.88rem;
    }

    /* Divider */
    hr { border-color: #2a2f45; }

    /* DataFrames */
    [data-testid="stDataFrame"] { border-radius: 8px; }

    /* Hide Streamlit default footer */
    footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Bootstrap DB if missing ────────────────────────────────────────────────────
if not db_utils.db_exists():
    import sqlite3
    conn = sqlite3.connect(db_utils.DB_PATH)
    create_schema(conn)
    seed_db(conn)
    conn.close()

# ── Alert helper (derived from live data) ─────────────────────────────────────
def _build_alerts(beds: pd.DataFrame, equipment: pd.DataFrame,
                  warn_t: int, crit_t: int) -> list[dict]:
    alerts = []
    for _, row in beds[beds["occupancy_pct"] >= crit_t].iterrows():
        alerts.append({"level": "critical",
            "message": f"🔴 {row['branch']} › {row['department']}: Bed occupancy at {row['occupancy_pct']}%"})
    for _, row in beds[(beds["occupancy_pct"] >= warn_t) & (beds["occupancy_pct"] < crit_t)].iterrows():
        alerts.append({"level": "warn",
            "message": f"🟡 {row['branch']} › {row['department']}: Bed occupancy at {row['occupancy_pct']}%"})
    for _, row in beds[beds["icu_occupancy_pct"] >= crit_t].iterrows():
        alerts.append({"level": "critical",
            "message": f"🔴 ICU CRITICAL — {row['branch']} › {row['department']}: {row['icu_available']} ICU bed(s) left"})
    for _, row in equipment[equipment["operational_pct"] < 50].iterrows():
        alerts.append({"level": "critical",
            "message": f"🔴 Equipment low — {row['branch']}: {row['equipment']} only {row['operational']} of {row['total']} operational"})
    return alerts[:12]

# ── Session state ──────────────────────────────────────────────────────────────
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = _now_ist()
if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = False
if "refresh_interval" not in st.session_state:
    st.session_state.refresh_interval = 30

# ── Sidebar controls ───────────────────────────────────────────────────────────
with st.sidebar:
    st.image(
        "https://img.icons8.com/fluency/96/hospital.png",
        width=56,
    )
    st.markdown("## 🏥 HospVision")
    st.markdown("<small style='color:#7c86c4'>Resource Management System</small>", unsafe_allow_html=True)
    st.markdown("---")

    st.markdown('<div class="section-header">Filters</div>', unsafe_allow_html=True)
    all_branches = db_utils.get_branch_list()
    selected_branches = st.multiselect(
        "Hospital Branch",
        options=all_branches,
        default=all_branches,
        key="sel_branches",
    )
    if not selected_branches:
        selected_branches = all_branches

    bed_df_all = db_utils.get_bed_occupancy()
    all_depts = sorted(bed_df_all[bed_df_all["branch"].isin(selected_branches)]["department"].unique().tolist())
    selected_depts = st.multiselect(
        "Department",
        options=all_depts,
        default=[],
        placeholder="All departments",
        key="sel_depts",
    )

    st.markdown("---")
    st.markdown('<div class="section-header">Live Refresh</div>', unsafe_allow_html=True)
    auto = st.toggle("Auto-refresh", value=st.session_state.auto_refresh, key="auto_refresh_toggle")
    st.session_state.auto_refresh = auto
    interval = st.select_slider(
        "Interval (seconds)",
        options=[10, 15, 30, 60, 120],
        value=st.session_state.refresh_interval,
        disabled=not auto,
        key="interval_slider",
    )
    st.session_state.refresh_interval = interval

    if st.button("🔄 Refresh Now", width="stretch"):
        st.session_state.last_refresh = _now_ist()
        st.cache_data.clear()
        st.rerun()

    elapsed = (_now_ist() - st.session_state.last_refresh).seconds
    st.caption(f"Last refreshed: {st.session_state.last_refresh.strftime('%H:%M:%S')} ({elapsed}s ago)")

    st.markdown("---")
    st.markdown('<div class="section-header">Thresholds</div>', unsafe_allow_html=True)
    warn_thresh = st.slider("Warning occupancy %", 50, 90, 75, key="warn_thresh")
    crit_thresh = st.slider("Critical occupancy %", 60, 99, 90, key="crit_thresh")

# ── Auto-refresh trigger ───────────────────────────────────────────────────────
if st.session_state.auto_refresh:
    elapsed = (_now_ist() - st.session_state.last_refresh).total_seconds()
    if elapsed >= st.session_state.refresh_interval:
        st.session_state.last_refresh = _now_ist()
        st.cache_data.clear()
        st.rerun()
    remaining = max(0, int(st.session_state.refresh_interval - elapsed))
    st.sidebar.caption(f"Next refresh in {remaining}s")

# ── Load data from SQLite ──────────────────────────────────────────────────────
@st.cache_data(ttl=10)
def _load_beds():
    return db_utils.get_bed_occupancy()

@st.cache_data(ttl=10)
def _load_equipment():
    return db_utils.get_equipment_status()

@st.cache_data(ttl=10)
def _load_trend():
    return db_utils.get_occupancy_trend(hours=24)

bed_df_full = _load_beds()
eq_df_full  = _load_equipment()
trend_df    = _load_trend()

# Apply filters
bed_df = bed_df_full[bed_df_full["branch"].isin(selected_branches)].copy()
if selected_depts:
    bed_df = bed_df[bed_df["department"].isin(selected_depts)]

eq_df    = eq_df_full[eq_df_full["branch"].isin(selected_branches)].copy()
trend_df = trend_df[trend_df["branch"].isin(selected_branches)].copy()

alerts = _build_alerts(bed_df, eq_df, warn_thresh, crit_thresh)

# ── Header ─────────────────────────────────────────────────────────────────────
col_title, col_time = st.columns([4, 1])
with col_title:
    st.markdown("## 🏥 HospVision Dashboard")
    st.caption(f"Monitoring {len(selected_branches)} branch(es) · {len(bed_df)} department views")
with col_time:
    _ts = _now_ist()
    st.markdown(
        f"<div style='text-align:right;padding-top:14px;color:#7c86c4;font-size:0.85rem'>"
        f"<b style='font-size:1.1rem;color:#e8eaf0'>{_ts.strftime('%H:%M:%S')}</b><br>"
        f"{_ts.strftime('%A, %d %b %Y')} IST</div>",
        unsafe_allow_html=True,
    )

st.markdown("---")

# ── KPI summary row ────────────────────────────────────────────────────────────
total_beds      = int(bed_df["total_beds"].sum())
total_occupied  = int(bed_df["occupied_beds"].sum())
total_available = int(bed_df["available_beds"].sum())
avg_occupancy   = round(bed_df["occupancy_pct"].mean(), 1)
total_icu       = int(bed_df["icu_total"].sum())
icu_occupied    = int(bed_df["icu_occupied"].sum())
icu_available   = int(bed_df["icu_available"].sum())
icu_pct         = round(icu_occupied / total_icu * 100, 1) if total_icu else 0
total_equipment = int(eq_df["total"].sum())
eq_operational  = int(eq_df["operational"].sum())
eq_pct          = round(eq_operational / total_equipment * 100, 1) if total_equipment else 0

delta_occ  = f"{'▲' if avg_occupancy > 75 else '▼'} vs 75% target"
delta_icu  = f"{'▲' if icu_pct > 85 else '▼'} vs 85% threshold"

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Total Beds",        f"{total_beds:,}")
k2.metric("Occupied Beds",     f"{total_occupied:,}", f"{avg_occupancy}% occupancy")
k3.metric("Available Beds",    f"{total_available:,}", delta_occ)
k4.metric("ICU Beds (total)",  f"{total_icu:,}")
k5.metric("ICU Available",     f"{icu_available:,}", f"{icu_pct}% occupied")
k6.metric("Equipment Up",      f"{eq_operational:,}/{total_equipment:,}", f"{eq_pct}% operational")

st.markdown("<br>", unsafe_allow_html=True)

# ── Alert panel ────────────────────────────────────────────────────────────────
if alerts:
    critical_alerts = [a for a in alerts if a["level"] == "critical"]
    warn_alerts     = [a for a in alerts if a["level"] == "warn"]
    with st.expander(
        f"⚠️ Active Alerts — {len(critical_alerts)} critical, {len(warn_alerts)} warning",
        expanded=len(critical_alerts) > 0,
    ):
        for a in alerts:
            css_class = "alert-banner" if a["level"] == "critical" else "info-banner"
            st.markdown(f'<div class="{css_class}">{a["message"]}</div>', unsafe_allow_html=True)
else:
    st.markdown(
        '<div class="info-banner">✅ All resources within normal thresholds</div>',
        unsafe_allow_html=True,
    )

st.markdown("---")

# ── Charts row 1: Bed occupancy gauge + ICU bar ────────────────────────────────
st.markdown('<div class="section-header">Bed & ICU Occupancy by Branch</div>', unsafe_allow_html=True)
c1, c2 = st.columns([1, 2])

with c1:
    # Gauge for overall occupancy
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=avg_occupancy,
        delta={"reference": 75, "valueformat": ".1f"},
        number={"suffix": "%", "font": {"size": 42, "color": "#e8eaf0"}},
        title={"text": "Overall Bed Occupancy", "font": {"size": 13, "color": "#8b93b5"}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "#8b93b5", "tickfont": {"color": "#8b93b5"}},
            "bar":  {"color": "#3b82f6"},
            "steps": [
                {"range": [0, warn_thresh],  "color": "#14432a"},
                {"range": [warn_thresh, crit_thresh], "color": "#3f2d05"},
                {"range": [crit_thresh, 100], "color": "#3f0f0f"},
            ],
            "threshold": {
                "line": {"color": "#ef4444", "width": 3},
                "thickness": 0.75,
                "value": crit_thresh,
            },
            "bgcolor": "#1e2130",
        },
    ))
    fig_gauge.update_layout(
        height=260, margin=dict(l=20, r=20, t=40, b=10),
        paper_bgcolor="#1e2130", font_color="#e8eaf0",
    )
    st.plotly_chart(fig_gauge, width="stretch")

with c2:
    # Grouped bar: occupied vs available per branch
    branch_agg = bed_df.groupby("branch").agg(
        occupied=("occupied_beds", "sum"),
        available=("available_beds", "sum"),
        icu_occ=("icu_occupied", "sum"),
        icu_avail=("icu_available", "sum"),
    ).reset_index()

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(name="Occupied",  x=branch_agg["branch"], y=branch_agg["occupied"],  marker_color="#3b82f6"))
    fig_bar.add_trace(go.Bar(name="Available", x=branch_agg["branch"], y=branch_agg["available"], marker_color="#22c55e"))
    fig_bar.add_trace(go.Bar(name="ICU Occupied", x=branch_agg["branch"], y=branch_agg["icu_occ"],   marker_color="#f97316"))
    fig_bar.add_trace(go.Bar(name="ICU Available",x=branch_agg["branch"], y=branch_agg["icu_avail"], marker_color="#a78bfa"))
    fig_bar.update_layout(
        barmode="group", height=260,
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="#1e2130", plot_bgcolor="#1e2130",
        font_color="#e8eaf0",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font_size=11),
        xaxis=dict(gridcolor="#2a2f45"),
        yaxis=dict(gridcolor="#2a2f45"),
        title=dict(text="Beds by Branch", font=dict(size=13, color="#8b93b5")),
    )
    st.plotly_chart(fig_bar, width="stretch")

# ── Occupancy trend ────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">24-Hour Occupancy Trend</div>', unsafe_allow_html=True)

fig_trend = px.line(
    trend_df, x="timestamp", y="occupancy_pct", color="branch",
    labels={"timestamp": "", "occupancy_pct": "Occupancy %", "branch": "Branch"},
    color_discrete_sequence=["#3b82f6","#22c55e","#f97316","#a78bfa","#f43f5e"],
)
fig_trend.add_hline(y=crit_thresh, line_dash="dot", line_color="#ef4444",
                    annotation_text=f"Critical ({crit_thresh}%)", annotation_font_color="#ef4444")
fig_trend.add_hline(y=warn_thresh,  line_dash="dot", line_color="#fbbf24",
                    annotation_text=f"Warning ({warn_thresh}%)", annotation_font_color="#fbbf24")
fig_trend.update_traces(line_width=2)
fig_trend.update_layout(
    height=280, margin=dict(l=0, r=0, t=20, b=0),
    paper_bgcolor="#1e2130", plot_bgcolor="#1e2130",
    font_color="#e8eaf0",
    xaxis=dict(gridcolor="#2a2f45"),
    yaxis=dict(gridcolor="#2a2f45", range=[20, 105]),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    hovermode="x unified",
)
st.plotly_chart(fig_trend, width="stretch")

st.markdown("---")

# ── Department-level heatmap ───────────────────────────────────────────────────
st.markdown('<div class="section-header">Department Occupancy Heatmap</div>', unsafe_allow_html=True)

pivot = bed_df.pivot_table(index="department", columns="branch", values="occupancy_pct", aggfunc="mean")
pivot = pivot.reindex(columns=[b for b in db_utils.get_branch_list() if b in pivot.columns])

fig_heat = go.Figure(go.Heatmap(
    z=pivot.values,
    x=pivot.columns.tolist(),
    y=pivot.index.tolist(),
    colorscale=[
        [0.0,  "#0f3460"],
        [0.55, "#14432a"],
        [0.75, "#3f2d05"],
        [0.90, "#7f1d1d"],
        [1.0,  "#ef4444"],
    ],
    zmin=0, zmax=100,
    text=[[f"{v:.0f}%" if not math.isnan(v) else "N/A" for v in row] for row in pivot.values],
    texttemplate="%{text}",
    textfont={"size": 11},
    hovertemplate="<b>%{y}</b> @ %{x}<br>Occupancy: %{z:.1f}%<extra></extra>",
    colorbar=dict(title=dict(text="Occ %", font=dict(color="#8b93b5")), tickfont=dict(color="#e8eaf0")),
))
fig_heat.update_layout(
    height=max(300, len(pivot) * 32 + 60),
    margin=dict(l=0, r=0, t=10, b=0),
    paper_bgcolor="#1e2130", plot_bgcolor="#1e2130",
    font_color="#e8eaf0",
    xaxis=dict(side="top"),
)
st.plotly_chart(fig_heat, width="stretch")

st.markdown("---")

# ── Equipment status ───────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Critical Equipment Status</div>', unsafe_allow_html=True)

eq_c1, eq_c2 = st.columns([3, 2])

with eq_c1:
    # Stacked bar by equipment type across selected branches
    eq_agg = eq_df.groupby("equipment").agg(
        operational=("operational", "sum"),
        maintenance=("maintenance", "sum"),
        out_of_service=("out_of_service", "sum"),
    ).reset_index().sort_values("operational", ascending=True)

    fig_eq = go.Figure()
    fig_eq.add_trace(go.Bar(name="Operational",     y=eq_agg["equipment"], x=eq_agg["operational"],     orientation="h", marker_color="#22c55e"))
    fig_eq.add_trace(go.Bar(name="Maintenance",     y=eq_agg["equipment"], x=eq_agg["maintenance"],     orientation="h", marker_color="#fbbf24"))
    fig_eq.add_trace(go.Bar(name="Out of Service",  y=eq_agg["equipment"], x=eq_agg["out_of_service"],  orientation="h", marker_color="#ef4444"))
    fig_eq.update_layout(
        barmode="stack", height=340,
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="#1e2130", plot_bgcolor="#1e2130",
        font_color="#e8eaf0",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font_size=11),
        xaxis=dict(gridcolor="#2a2f45"),
        yaxis=dict(gridcolor="#2a2f45"),
        title=dict(text="Units by Equipment Type", font=dict(size=13, color="#8b93b5")),
    )
    st.plotly_chart(fig_eq, width="stretch")

with eq_c2:
    # Donut for overall equipment health
    total_op  = int(eq_df["operational"].sum())
    total_mnt = int(eq_df["maintenance"].sum())
    total_oos = int(eq_df["out_of_service"].sum())

    fig_donut = go.Figure(go.Pie(
        labels=["Operational", "Maintenance", "Out of Service"],
        values=[total_op, total_mnt, total_oos],
        hole=0.6,
        marker_colors=["#22c55e", "#fbbf24", "#ef4444"],
        textfont_size=12,
    ))
    fig_donut.update_layout(
        height=280,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="#1e2130",
        font_color="#e8eaf0",
        showlegend=True,
        legend=dict(orientation="v", font_size=11),
        annotations=[dict(
            text=f"<b>{round(total_op/(total_op+total_mnt+total_oos)*100)}%</b><br>Up",
            font_size=18, font_color="#22c55e",
            showarrow=False,
        )],
    )
    st.plotly_chart(fig_donut, width="stretch")

    # Mini table: branches with any equipment issues
    issue_eq = eq_df[eq_df["out_of_service"] > 0][["branch","equipment","out_of_service"]].copy()
    issue_eq.columns = ["Branch","Equipment","OOS"]
    issue_eq = issue_eq.sort_values("OOS", ascending=False).head(8)
    if not issue_eq.empty:
        st.markdown('<p style="font-size:0.78rem;color:#8b93b5;margin-bottom:4px">OUT-OF-SERVICE ITEMS</p>', unsafe_allow_html=True)
        st.dataframe(
            issue_eq,
            hide_index=True,
            width="stretch",
            height=180,
        )

st.markdown("---")

# ── Department-level detail table ─────────────────────────────────────────────
st.markdown('<div class="section-header">Department Detail</div>', unsafe_allow_html=True)

def _status_badge(pct):
    if pct >= crit_thresh:
        return "🔴 Critical"
    elif pct >= warn_thresh:
        return "🟡 Warning"
    else:
        return "🟢 Normal"

detail_df = bed_df[[
    "branch","department","total_beds","occupied_beds","available_beds",
    "occupancy_pct","icu_total","icu_occupied","icu_available","icu_occupancy_pct"
]].copy()
detail_df["Status"] = detail_df["occupancy_pct"].apply(_status_badge)
detail_df.columns = [
    "Branch","Department","Total Beds","Occupied","Available",
    "Occ %","ICU Total","ICU Occ","ICU Avail","ICU Occ %","Status"
]
detail_df = detail_df.sort_values("Occ %", ascending=False)

st.dataframe(
    detail_df,
    hide_index=True,
    width="stretch",
    height=min(500, 40 * len(detail_df) + 40),
    column_config={
        "Occ %":     st.column_config.ProgressColumn("Occ %",     min_value=0, max_value=100, format="%.1f%%"),
        "ICU Occ %": st.column_config.ProgressColumn("ICU Occ %", min_value=0, max_value=100, format="%.1f%%"),
    },
)

st.markdown("---")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown(
    "<div style='text-align:center;color:#57606a;font-size:0.75rem;padding:10px 0'>"
    "HospVision v1.0 · Real-Time Resource Management · Data refreshes automatically when Live Refresh is enabled"
    "</div>",
    unsafe_allow_html=True,
)
