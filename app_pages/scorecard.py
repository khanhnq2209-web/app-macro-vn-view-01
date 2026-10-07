"""Scorecard theo phân khúc: điểm, chi tiết, lịch sử. Chỉ xem bản đã lưu."""

import json

import pandas as pd
import streamlit as st

from macro_app import profiles as pf
from macro_app.metrics.scorecard import load_settings
from macro_app.metrics.transforms import measure
from macro_app.ui import components as ui
from macro_app.ui import data, monitor, scorecard_view, sidebar

st.title("Scorecard theo phân khúc")
ss = st.session_state
saved_all = pf.load_profiles()
if not saved_all:
    st.info("Chưa có bộ cấu hình nào trong config/profiles/.")
    st.stop()
default = pf.default_profile()
latest = data.latest()
catalog = data.catalog_map()
settings = load_settings()
group_names = {g: f"{g} · {r['name']}" for g, r in data.impact_rules()["groups"].items()}

options = list(saved_all)
if ss.get("sc_profile") not in options:
    wanted = st.query_params.get("profile")
    ss["sc_profile"] = wanted if wanted in options else default
top = st.columns([2, 3, 1])
profile = top[0].selectbox(
    "Bộ cấu hình",
    options,
    format_func=lambda s: saved_all[s]["name"] + (" · mặc định" if s == default else ""),
    key="sc_profile",
)
prof = saved_all[profile]
segments = list(prof["segments"])
seg_key = f"sc_segment_{profile}"
if ss.get(seg_key) not in segments:
    wanted = st.query_params.get("segment")
    ss[seg_key] = wanted if wanted in segments else (segments[0] if segments else None)
with top[1]:
    segment = (
        st.segmented_control(
            "Phân khúc",
            segments,
            format_func=lambda s: prof["segments"][s]["name"],
            key=seg_key,
        )
        if segments
        else None
    ) or (segments[0] if segments else None)
if sidebar.is_admin():
    top[2].write("")
    top[2].page_link("app_pages/scorecard_config.py", label="Sửa cấu hình", icon="⚙️")
if prof.get("description"):
    st.caption(prof["description"])
if not segment:
    st.info("Bộ này chưa có phân khúc.")
    st.stop()

card = prof["segments"][segment]
payload = json.dumps(pf.clean_card(card), ensure_ascii=False, sort_keys=True)
table, total, hist = data.scorecard_eval(payload, data.build_stamp())
names = {c: i.name for c, i in catalog.items()}
head = pd.Series({**total, "name": card["name"]})
st.html(scorecard_view.header_html(head, card["description"], names))
if table.empty:
    st.info("Phân khúc chưa có chỉ số.")
else:
    sparks = {}
    for r in card["rows"]:
        if r["code"] in catalog:
            s = measure(data.series(r["code"]), catalog[r["code"]].frequency, r.get("measure"))
            s = s[s.index > s.index[-1] - pd.DateOffset(years=3)] if not s.empty else s
            status = table.set_index("code")["status"].get(r["code"], "none")
            sparks[r["code"]] = monitor.sparkline(s, status)
    st.html(
        scorecard_view.table_html(table, latest, catalog, group_names, total=total, sparks=sparks)
    )
with st.expander("Tín hiệu dự báo: lãi suất Fed theo FedWatch", expanded=False):
    lat = latest.set_index("code")
    upper = lat.loc["fed_upper", "value"] if "fed_upper" in lat.index else float("nan")
    st.html(scorecard_view.fed_path_html(data.fed_path(), upper))
    st.caption(
        "Kỳ vọng (Fed) và mục tiêu Chính phủ được chấm theo ngưỡng của dòng. Không tính vào điểm."
    )
years = (
    st.segmented_control(
        "Nhìn lại",
        [1, 3, 5, 10],
        default=5,
        format_func=lambda y: f"{y} năm",
        key="sc_lookback",
    )
    or 5
)
if not hist.dropna(subset=["score"]).empty:
    shown = hist[hist["date"] > hist["date"].max() - pd.DateOffset(years=years)]
    st.plotly_chart(
        scorecard_view.history_chart(shown, settings["rating_bands"], "Điểm theo tháng"),
        width="stretch",
        config={"displayModeBar": False},
        key="sc_hist",
    )
st.html(
    "<p class='mc-note'>Điểm = tổng có trọng số của mức từng chỉ số (+2 đến −2), trọng số chia đều "
    "theo trụ cột. Chỉ số thiếu hoặc số cũ không tính. Ngưỡng và thang điểm đang chờ duyệt.</p>"
)
ui.footer()
