"""Tổng quan, dùng để chụp vào slide."""

import html

import pandas as pd
import streamlit as st

from macro_app import fmt
from macro_app.config import load_sources
from macro_app.metrics.status import STATUS_LABEL
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
st.html(monitor.summary_strip(latest, fmt.date(built[:10]) + built[10:]))


def names_with(flag: str) -> list[str]:
    return latest.loc[latest["flags"].fillna("").str.contains(flag), "name"].tolist()


alerts = []
stale = names_with("stale")
if stale:
    alerts.append(
        f'<span title="{html.escape(", ".join(stale))}">{len(stale)} chỉ số chưa có số mới</span>'
    )
rebased = names_with("rebase_suspect")
if rebased:
    alerts.append(
        f'<span title="{html.escape(", ".join(rebased))}">{len(rebased)} chuỗi GDP gãy năm gốc, chưa xếp màu</span>'
    )
unverified = names_with("unit_unverified")
if unverified:
    alerts.append(f"Chưa xác minh đơn vị: {html.escape(', '.join(unverified))}")
max_age = pd.Timedelta(hours=load_sources().get("cache_max_age_hours", 24))
for name, fetched in (meta.get("cache_fetched_at") or {}).items():
    if fetched and pd.Timestamp.now(tz="UTC") - pd.Timestamp(fetched) > max_age:
        alerts.append(f"{name.upper()} lấy từ cache ngày {fmt.date(fetched)}")
failed = [k for k, v in st.session_state.get("refresh_results", {}).items() if v != "ok"]
if failed or meta.get("source_errors"):
    alerts.append("Lần cập nhật gần nhất lỗi: " + ", ".join(failed or meta["source_errors"]))
if alerts:
    st.html(f'<div class="ma">⚠ {" · ".join(alerts)}</div>')

# Chỉ tính đổi màu do số liệu, bỏ qua đổi do sửa ngưỡng.
hist = data.history()
changes = []
if not hist.empty:
    h = hist[hist["reason"] == "data"].copy()
    h["run_at"] = pd.to_datetime(h["run_at"])
    h = h.sort_values("run_at")
    h["prev_status"] = h.groupby("code")["status"].shift()
    recent = h[
        (h["run_at"] >= pd.Timestamp.now() - pd.Timedelta(days=30))
        & h["prev_status"].notna()
        & (h["status"] != h["prev_status"])
    ]
    names = latest.set_index("code")["name"]
    changes = [
        f"<b>{html.escape(names.get(r['code'], r['code']))}</b> "
        f"{STATUS_LABEL.get(r['prev_status'], r['prev_status'])} → {STATUS_LABEL.get(r['status'], r['status'])}"
        f" ({r['run_at']:%d/%m})"
        for r in recent.sort_values("run_at", ascending=False)
        .drop_duplicates("code")
        .to_dict("records")
    ]
    if len(changes) > 6:
        changes = [*changes[:6], f"và {len(changes) - 6} chỉ số khác"]
st.html(
    f'<div class="mr">Đổi màu trong 30 ngày: {" · ".join(changes) if changes else "không có"}</div>'
)

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

st.caption("Chấm màu: vị trí so với ngưỡng của chỉ số.")

if present:
    with st.container(key="present_exit"):
        if st.button("Thoát chế độ trình bày"):
            sidebar.set_presentation(False)
            st.rerun()
ui.footer()
