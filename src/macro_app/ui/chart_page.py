"""Bố cục chung của trang Quốc tế và Việt Nam: chọn nhóm, lưới chart 2 cột, bảng số liệu, tải CSV."""

from __future__ import annotations

import streamlit as st

from macro_app.ui import components as ui

GROUP_NAMES = {
    "A1": "A1 Fed và USD",
    "A2": "A2 Năng lượng",
    "A3": "A3 Kim loại",
    "A4": "A4 Thuế quan Mỹ",
    "A5": "A5 Toàn cầu",
    "B1": "B1 Tăng trưởng",
    "B2": "B2 Lạm phát, tỷ giá",
    "B3": "B3 Lãi suất",
    "B4": "B4 Tín dụng",
    "C1": "C1 Đất đai",
    "D2": "D2 Đầu tư công",
    "E1": "E1 FDI",
}


def chart_grid(charts: list[dict], key: str, per_row: int = 2) -> list[str]:
    codes: list[str] = []
    for start in range(0, len(charts), per_row):
        cols = st.columns(per_row)
        for j, (col, chart) in enumerate(zip(cols, charts[start : start + per_row], strict=False)):
            with col:
                ui.chart_from_view(chart, key=f"{key}_{start + j}")
            codes += [c for c in chart.get("codes", []) if c not in codes]
    return codes


def group_section(charts: list[dict], key: str) -> None:
    groups = list(dict.fromkeys(c.get("group", "") for c in charts))
    if not groups:
        st.info("View đang chọn chưa có biểu đồ cho trang này.")
        return
    picked = (
        st.segmented_control(
            "Nhóm chỉ số",
            groups,
            default=groups[0],
            format_func=lambda g: GROUP_NAMES.get(g, g),
            key=f"{key}_group",
        )
        or groups[0]
    )
    selected = [c for c in charts if c.get("group") == picked]
    codes = chart_grid(selected, key=f"{key}_{picked}")
    st.markdown("##### Số liệu mới nhất")
    ui.stats_table(codes)
    ui.download_series_button(codes, key=f"{key}_{picked}_dl")
