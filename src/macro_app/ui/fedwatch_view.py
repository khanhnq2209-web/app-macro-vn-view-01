"""Tab FedWatch trên trang Quốc tế."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from macro_app import fmt
from macro_app.charts import theme
from macro_app.metrics import fedwatch_table as fw
from macro_app.ui import data, sidebar

SOURCE_LABEL = {
    "computed": "Tính từ giá hợp đồng ZQ (cách tính của CME)",
    "quikstrike": "CME FedWatch (QuikStrike)",
}
NOTE = "Xác suất suy ra từ giá hợp đồng tương lai Fed Funds 30 ngày."


def _ranges() -> pd.DataFrame:
    lo, hi = data.series("fed_lower"), data.series("fed_upper")
    both = pd.concat({"low_bp": lo * 100, "high_bp": hi * 100}, axis=1).dropna()
    return both.round().astype(int).rename_axis("date").reset_index()


def _current_range() -> tuple[int, int] | None:
    lo, hi = data.series("fed_lower"), data.series("fed_upper")
    if lo.empty or hi.empty:
        return None
    return round(lo.iloc[-1] * 100), round(hi.iloc[-1] * 100)


def _history_chart(summ: pd.DataFrame, meeting: pd.Timestamp) -> go.Figure:
    part = summ[summ["meeting_date"] == meeting].sort_values("asof")
    fig = go.Figure()
    for i, (col, name) in enumerate((("cut", "Giảm"), ("hold", "Giữ nguyên"), ("hike", "Tăng"))):
        fig.add_trace(
            go.Scatter(
                x=part["asof"],
                y=part[col] * 100,
                name=name,
                mode="lines",
                line={"color": theme.CATEGORICAL[i], "width": 2},
                hovertemplate="%{y:.1f}%<extra>" + name + "</extra>",
            )
        )
    theme.apply_theme(fig, f"Xác suất cho kỳ họp {fmt.date(meeting)} theo thời gian", "%")
    fig.update_yaxes(range=[0, 100])
    return fig


def render_fedwatch() -> None:
    tables = data.fedwatch()
    available = [k for k in ("computed", "quikstrike") if k in tables and not tables[k].empty]
    if sidebar.is_admin() is False:
        # Bản công khai chỉ hiện số tự tính.
        available = [k for k in available if k == "computed"]
    if not available:
        st.info("Chưa có dữ liệu FedWatch.")
        return
    source = st.radio(
        "Nguồn", available, format_func=SOURCE_LABEL.get, horizontal=True, key="fw_source"
    )
    df = tables[source]
    asof = fw.latest_asof(df)
    st.caption(f"{NOTE} Số liệu ngày {fmt.date(asof)} · {SOURCE_LABEL[source]}")
    current = _current_range()
    if current:
        st.markdown(f"Khoảng mục tiêu hiện tại: **{fw.range_label(*current)}%**")
        summ = fw.summary(df, _ranges())
        latest = summ[summ["asof"] == asof].copy()
        table = pd.DataFrame(
            {
                "Kỳ họp FOMC": latest["meeting_date"].map(fmt.date),
                "Khả năng cao nhất": latest["top_range"]
                + "% ("
                + latest["top_prob"].map(fmt.prob)
                + ")",
                "P(giảm)": latest["cut"].map(fmt.prob),
                "P(giữ)": latest["hold"].map(fmt.prob),
                "P(tăng)": latest["hike"].map(fmt.prob),
            }
        )
        st.dataframe(table, hide_index=True, width="stretch")
    mat = fw.matrix(df, asof)
    if not mat.empty:
        st.markdown("##### Ma trận xác suất theo khoảng lãi suất (%)")
        shown = mat.map(lambda p: fmt.prob(p) if pd.notna(p) else "")
        shown.index = [fmt.date(d) for d in mat.index]
        st.dataframe(shown, width="stretch")
    if current:
        meetings = sorted(summ["meeting_date"].unique())
        if meetings and summ["asof"].drop_duplicates().size > 1:
            meeting = st.selectbox("Kỳ họp", meetings, format_func=fmt.date, key="fw_meeting")
            st.plotly_chart(
                _history_chart(summ, pd.Timestamp(meeting)),
                width="stretch",
                config=theme.download_config("fedwatch_lich_su"),
                key="fw_hist",
            )
