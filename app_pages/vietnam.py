"""Trang 3: Việt Nam (nhóm B, C, D, E) và tab chỉ số dẫn xuất."""

import streamlit as st

from macro_app.ui import chart_page, sidebar
from macro_app.ui import components as ui

st.title("Việt Nam")
view = sidebar.current_view().get("vietnam", {})
tab_main, tab_derived, tab_sample = st.tabs(["Theo nhóm", "Dẫn xuất", "Mẫu lãi suất"])
with tab_main:
    chart_page.group_section(view.get("charts", []), key="vn")
with tab_derived:
    st.caption(
        "Lãi suất thực bằng lãi suất huy động 12 tháng bình quân Big4 (cuối tháng) trừ CPI so cùng kỳ. "
        "Tín dụng trừ M2 là chênh lệch hai tốc độ tăng từ đầu năm."
    )
    derived = view.get("derived", [])
    codes = chart_page.chart_grid(derived, key="vn_derived")
    st.markdown("##### Số liệu mới nhất")
    ui.stats_table(codes)
    ui.download_series_button(codes, key="vn_derived_dl")
with tab_sample:
    st.caption(
        "Lãi suất thực = lãi suất huy động 12 tháng bình quân Big4 trừ CPI so cùng kỳ (theo tháng). "
        "Lãi suất Fed là EFFR theo ngày."
    )
    codes = chart_page.chart_grid(view.get("sample", []), key="vn_sample")
    st.markdown("##### Số liệu mới nhất")
    ui.stats_table(codes)
    ui.download_series_button(codes, key="vn_sample_dl")
ui.footer()
