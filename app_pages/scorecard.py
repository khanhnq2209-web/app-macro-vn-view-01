"""Scorecard theo phân khúc: gauge + vì sao + độ tin cậy, bảng theo nhóm, lịch sử. Chỉ xem bản đã lưu."""

import json

import pandas as pd
import streamlit as st

from macro_app import fmt
from macro_app import profiles as pf
from macro_app.metrics import implications as im
from macro_app.metrics.scorecard import load_settings
from macro_app.metrics.transforms import measure
from macro_app.ui import components as ui
from macro_app.ui import data, monitor, profile_store, report_export, scorecard_view

CMP_LABEL = {1: "tháng trước", 3: "3 tháng trước", 12: "cùng kỳ năm ngoái"}
CMP_BUTTON = {1: "Tháng trước", 3: "3 tháng trước", 12: "Cùng kỳ năm ngoái"}

st.title("Scorecard theo phân khúc")
ss = st.session_state
store = profile_store.load()
saved_all = store["profiles"]
if store["error"]:
    st.warning(store["error"])
if not saved_all:
    st.info("Chưa có bộ cấu hình nào.")
    st.stop()
latest = data.latest()
catalog = data.catalog_map()
settings = load_settings()

options = list(saved_all)
if ss.get("sc_profile") not in options:
    wanted = st.query_params.get("profile")
    ss["sc_profile"] = wanted if wanted in options else store["default"]
top = st.columns([1.8, 1.8, 3.4, 1.25, 1.25], vertical_alignment="bottom")
profile = top[0].selectbox(
    "Bộ cấu hình",
    options,
    format_func=lambda s: (  # selectbox hiển thị chữ thường, không cần thoát Markdown
        saved_all[s]["name"] + (" · mặc định" if s == store["default"] else "")
    ),
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
            format_func=lambda s: fmt.md(prof["segments"][s]["name"]),
            key=seg_key,
        )
        if segments
        else None
    ) or (segments[0] if segments else None)
with top[2]:
    k = (
        st.segmented_control(
            "So sánh với", list(CMP_LABEL), format_func=CMP_BUTTON.get, default=1, key="sc_cmp"
        )
        or 1
    )
if not segment:
    st.info("Bộ này chưa có phân khúc.")
    st.stop()
card = prof["segments"][segment]


def open_config(step: int, code: str | None = None) -> None:
    ss["cfg_target"] = {"profile": profile, "segment": segment, "step": step, "code": code}
    st.switch_page("app_pages/scorecard_config.py")


with top[3].popover("⚙ Sửa cấu hình", width="stretch"):
    if st.button("Nhóm và tỷ trọng", key="sc_edit_groups", width="stretch"):
        open_config(2)
    codes = [r["code"] for r in card["rows"] if r["code"] in catalog]
    pick = st.selectbox(
        "Mốc của chỉ số", codes, format_func=lambda c: catalog[c].name, key="sc_edit_code"
    )
    if st.button("Sửa mốc chỉ số này", key="sc_edit_row", width="stretch", disabled=not codes):
        open_config(3, pick)


@st.cache_data(show_spinner="Đang tạo báo cáo…", max_entries=16)
def report_file(kind: str, payload: str, months: int, stamp: float, meta: tuple) -> bytes:
    """PDF hoặc Word của một phân khúc; cache theo nội dung nên bấm lại không tạo lại."""
    profile_name, saved_note, seg = meta
    table_r, total_r, _ = data.scorecard_eval(payload, stamp)
    lat = data.latest().set_index("code")["value"]
    notes_r = im.implications(
        json.loads(payload),
        table_r,
        {c: i.name for c, i in catalog.items()},
        im.load_notes(),
        seg=seg,
        fed=im.fed_outlook(data.fed_path(), lat.get("fed_upper", float("nan"))),
    )
    rep = report_export.build_report(
        profile=profile_name,
        card=json.loads(payload),
        table=table_r,
        total=total_r,
        latest=data.latest(),
        catalog=catalog,
        months=months,
        compare_label=CMP_LABEL[months],
        saved_note=saved_note,
        bands=settings["rating_bands"],
        implications=[(x["tone"], x["name"], x["text"]) for x in notes_r],
    )
    return report_export.to_pdf(rep) if kind == "pdf" else report_export.to_docx(rep)


with top[4].popover("⬇ Tải báo cáo", width="stretch"):
    st.caption("Báo cáo 1 trang: gauge, điểm, vì sao, độ tin cậy, bảng chỉ số theo nhóm.")
    if st.button("Tạo báo cáo", key="sc_make_report", type="primary", width="stretch"):
        ss["sc_report_for"] = (profile, segment, k)
    if ss.get("sc_report_for") == (profile, segment, k):
        saved = store["meta"].get(profile)
        note = (
            f"cập nhật {str(saved['saved_at'])[:10]} bởi {saved['saved_by']}"
            if saved
            else "bản gốc trong repo"
        )
        args = (
            json.dumps(pf.clean_card(card), ensure_ascii=False, sort_keys=True),
            k,
            data.build_stamp(),
            (prof["name"], note, segment),
        )
        stem = f"scorecard_{profile}_{segment}_{pd.Timestamp.now():%Y%m%d}"
        st.download_button(
            "Tải PDF",
            report_file("pdf", *args),
            f"{stem}.pdf",
            "application/pdf",
            key="sc_dl_pdf",
            width="stretch",
        )
        st.download_button(
            "Tải Word",
            report_file("docx", *args),
            f"{stem}.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="sc_dl_docx",
            width="stretch",
        )

draft = ss.get("cfg_draft")
if (
    draft
    and ss.get("cfg_bo") == profile
    and pf.is_dirty(draft, prof)
    and not ss.get("cfg_new", False)
):
    st.info(
        "Bạn có bản nháp chưa lưu cho bộ này ở trang Cấu hình. Trang này hiển thị bản đã lưu.",
        icon="✏️",
    )

payload = json.dumps(pf.clean_card(card), ensure_ascii=False, sort_keys=True)
table, total, hist = data.scorecard_eval(payload, data.build_stamp())
if table.empty:
    st.info("Phân khúc chưa có chỉ số.")
    st.stop()
names = {c: i.name for c, i in catalog.items()}
cmp = total["compare"][k]
bands = settings["rating_bands"]

c1, c2, c3 = st.columns([1.2, 1.15, 1.1])
with c1.container(border=True, height="stretch"):
    st.html(scorecard_view.card_head_html(card["name"], store["meta"].get(profile)))
    st.plotly_chart(
        scorecard_view.gauge_figure(total["score"], bands),
        width="stretch",
        config={"displayModeBar": False, "staticPlot": True},
        key="sc_gauge",
    )
    st.html(scorecard_view.score_html(total, cmp, CMP_LABEL[k]))
    st.html(scorecard_view.meaning_html(card.get("meaning", "")))
with c2.container(border=True, height="stretch"):  # vì sao + độ tin cậy chung một box
    st.html(scorecard_view.why_html(total["pillars"], cmp, CMP_LABEL[k], total["score"]))
    st.html('<hr class="sc3-sep">' + scorecard_view.trust_html(total, table, names, latest, bands))
fed_now = latest.set_index("code")["value"].get("fed_upper", float("nan"))
fed = im.fed_outlook(data.fed_path(), fed_now)
notes = im.implications(card, table, names, im.load_notes(), seg=segment, fed=fed, limit=5)
with c3:
    st.html(scorecard_view.implications_html(notes))

head = st.columns([3, 1.3], vertical_alignment="bottom")
head[0].subheader("Chi tiết chỉ số")
show_w = head[1].toggle("Hiện trọng số và đóng góp", value=False, key="sc_show_w")
sparks = {}
status_by = table.set_index("code")["status"]
for r in card["rows"]:
    if r["code"] in catalog:
        s = measure(data.series(r["code"]), catalog[r["code"]].frequency, r.get("measure"))
        s = s[s.index > s.index[-1] - pd.DateOffset(years=3)] if not s.empty else s
        sparks[r["code"]] = monitor.sparkline(s, status_by.get(r["code"], "none"))
st.html(
    scorecard_view.table_html(
        table,
        latest,
        catalog,
        card,
        total,
        cmp=cmp,
        cmp_label=CMP_LABEL[k],
        sparks=sparks,
        show_weights=show_w,
    )
)

hist_head = st.columns([3, 2], vertical_alignment="bottom")
hist_head[0].subheader("Điểm theo tháng")
with hist_head[1]:
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
        scorecard_view.history_chart(shown, bands),
        width="stretch",
        config={"displayModeBar": False},
        key="sc_hist",
    )
st.html(
    "<p class='mc-note'>Điểm = tổng có trọng số của mức từng chỉ số (+2 đến −2); tỷ trọng mặc định "
    "chia đều theo nhóm. Chỉ số thiếu hoặc số cũ không tính. Điểm từng tháng <b>tính lại theo cấu "
    "hình hiện tại</b>, chưa trừ độ trễ công bố số liệu: không phải tín hiệu đã biết tại thời điểm "
    "đó.</p>"
)
ui.footer()
