"""Tổng quan: số mới nhất các chỉ số chính, dùng để chụp vào slide."""

import html

import pandas as pd
import streamlit as st

from macro_app import fmt
from macro_app.config import load_sources
from macro_app.ui import components as ui
from macro_app.ui import data, monitor, sidebar

latest = data.latest()
meta = data.build_meta()
view = sidebar.current_view()
present = sidebar.presentation_mode()

st.title("Theo dõi vĩ mô · thị trường BĐS Việt Nam")
if latest.empty:
    st.warning("Chưa có dữ liệu. Chạy `python -m macro_app.cli build` trước.")
    st.stop()

built = meta.get("built_at", "")[:16].replace("T", " ")
st.caption(f"{len(latest)} chỉ số · cập nhật {fmt.date(built[:10])}{built[10:]}")


def names_with(flag: str) -> list[str]:
    return latest.loc[latest["flags"].fillna("").str.contains(flag), "name"].tolist()


# Chỉ báo chất lượng dữ liệu (số cũ, cache cũ, lỗi cập nhật); không chấm điểm ở trang này.
alerts = []
stale = names_with("stale")
if stale:
    alerts.append(
        f'<span title="{html.escape(", ".join(stale))}">{len(stale)} chỉ số chưa có số mới</span>'
    )
max_age = pd.Timedelta(hours=load_sources().get("cache_max_age_hours", 24))
for name, fetched in (meta.get("cache_fetched_at") or {}).items():
    if fetched and pd.Timestamp.now(tz="UTC") - pd.Timestamp(fetched) > max_age:
        alerts.append(f"{name.upper()} lấy từ cache ngày {fmt.date(fetched)}")
failed = [k for k, v in st.session_state.get("refresh_results", {}).items() if v != "ok"]
if failed or meta.get("source_errors"):
    alerts.append("Lần cập nhật gần nhất lỗi: " + ", ".join(failed or meta["source_errors"]))
if alerts:
    st.html(f'<div class="ma">⚠ {" · ".join(alerts)}</div>')

catalog = data.catalog_map()
rules = data.impact_rules()
group_names = {g: f"{g} · {r['name']}" for g, r in rules["groups"].items()}
by_code = latest.set_index("code")
blocks = view.get("overview", {}).get("blocks", [])
cols = st.columns(len(blocks) or 1, gap="large")
for col, block in zip(cols, blocks, strict=False):
    codes = [c for c in block.get("codes", []) if c in by_code.index]
    rows = by_code.loc[codes].reset_index()
    ctx = monitor.BlockContext(
        sparks={c: monitor.spark_points(data.series(c), catalog[c].frequency) for c in codes},
        decimals={c: catalog[c].decimals for c in codes},
        group_names=group_names,
    )
    with col:
        st.html(monitor.block_html(block.get("title", ""), rows, ctx))

if present:
    with st.container(key="present_exit"):
        if st.button("Thoát chế độ trình bày"):
            sidebar.set_presentation(False)
            st.rerun()
ui.footer()
