"""Bộ ngưỡng có tên: bật/tắt, xem, lưu ngưỡng hiện tại thành bộ mới."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from macro_app import admin
from macro_app.build import rescore
from macro_app.config import active_threshold_sets, load_threshold_sets
from macro_app.metrics.status import cuts_of
from macro_app.ui import data
from macro_app.ui.threshold_editor import METHOD_LABEL, SIDE_LABEL, cuts_text


def items_table(items: dict) -> pd.DataFrame:
    catalog = data.catalog_map()
    rows = [
        {
            "Chỉ số": catalog[code].name if code in catalog else code,
            "Kiểu": METHOD_LABEL.get(cfg.get("method"), cfg.get("method")),
            "Chiều": SIDE_LABEL.get(cfg.get("side", "both")),
            "Mốc": cuts_text(cuts_of(cfg)),
            "N năm": cfg.get("window_years", ""),
            "Mô tả": cfg.get("description", ""),
        }
        for code, cfg in items.items()
    ]
    return pd.DataFrame(rows)


def render(*, editable: bool) -> None:
    sets = load_threshold_sets()
    active = [s for s in active_threshold_sets() if s in sets]
    st.markdown("#### Bộ ngưỡng")
    if not sets:
        st.caption("Chưa có bộ ngưỡng nào.")
    chosen = st.multiselect(
        "Bộ đang bật (trùng chỉ số thì bộ chọn sau đè bộ trước)",
        list(sets),
        default=active,
        format_func=lambda s: sets[s]["name"],
        disabled=not editable,
        key="thr_sets_active",
    )
    if editable and chosen != active:
        admin.set_active_threshold_sets(chosen)
        with st.spinner("Đang tính lại…"):
            rescore()
        st.cache_data.clear()
        st.toast("Đã áp dụng bộ ngưỡng")
        st.rerun()
    for slug, s in sets.items():
        mark = " · đang bật" if slug in active else ""
        with st.expander(f"{s['name']} · {len(s['items'])} chỉ số{mark}"):
            if s.get("description"):
                st.caption(s["description"])
            st.dataframe(items_table(s["items"]), hide_index=True, width="stretch")
    if editable:
        with st.expander("Lưu ngưỡng hiện tại thành bộ mới"):
            current = admin.current_overrides()
            st.caption(
                f"Lưu {len(current)} ngưỡng riêng đang hiệu lực (từ bộ đang bật và sửa tay)."
            )
            name = st.text_input("Tên bộ", key="thr_sets_name")
            desc = st.text_input("Mô tả bộ", key="thr_sets_desc")
            if st.button("Lưu bộ", key="thr_sets_save", disabled=not name.strip() or not current):
                path = admin.save_threshold_set(name, desc, current)
                st.toast(f"Đã lưu bộ {name} ({path.name})")
                st.rerun()
