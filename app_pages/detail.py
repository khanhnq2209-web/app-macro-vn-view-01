"""Chi tiết một chỉ số."""

import pandas as pd
import streamlit as st

from macro_app import fmt
from macro_app.charts.series import RANGE_YEARS, TRANSFORM_LABEL
from macro_app.metrics.impact import TAG_LABEL, TREND_LABEL
from macro_app.metrics.quality import FLAG_LABEL
from macro_app.metrics.status import STATUS_LABEL
from macro_app.ui import components as ui
from macro_app.ui import data, sidebar, threshold_form

catalog = data.catalog_map()
latest = data.latest().set_index("code")
codes = [c for c in catalog if c in latest.index]
default = st.query_params.get("code") or st.session_state.get("detail_code") or codes[0]
code = st.selectbox(
    "Chỉ số",
    codes,
    index=codes.index(default) if default in codes else 0,
    format_func=lambda c: f"{catalog[c].group} · {catalog[c].name}",
    key="detail_select",
)
st.session_state["detail_code"] = code
ind, rec = catalog[code], latest.loc[code]


def _forward_line(code: str) -> dict:
    """Đường kỳ vọng FedWatch cho lãi Fed theo các kỳ họp tới."""
    if code not in ("fed_upper", "fed_lower"):
        return {}
    path = data.fed_path()
    if path.empty:
        return {}
    ahead = path[path["meeting_date"] > path["asof"].max()]
    col = "exp_upper" if code == "fed_upper" else "exp_lower"
    series = pd.Series(ahead[col].to_numpy(), index=pd.DatetimeIndex(ahead["meeting_date"]))
    return {"forward": series, "forward_name": "Kỳ vọng FedWatch"}


st.title(ind.name)
c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "Giá trị mới nhất",
    fmt.value(rec["value"], ind.unit, ind.decimals),
    fmt.change(rec["change"], ind.change_unit) if rec["value"] == rec["value"] else None,
    delta_color="off",
)
c2.metric("Kỳ", fmt.period(rec["period"], ind.frequency))
c3.metric("Trạng thái ngưỡng", STATUS_LABEL.get(rec["status"], rec["status"]))
c4.metric(
    "Tác động BĐS",
    TAG_LABEL.get(rec["favorability"], "—"),
    TREND_LABEL.get(rec["trend"], ""),
    delta_color="off",
)

o1, o2, o3 = st.columns(3)
rng = o1.segmented_control("Khoảng", list(RANGE_YEARS), default="5Y", key="detail_range") or "5Y"
how = (
    o2.segmented_control(
        "Biến đổi",
        list(TRANSFORM_LABEL),
        default="level",
        format_func=TRANSFORM_LABEL.get,
        key="detail_transform",
    )
    or "level"
)
kind = (
    o3.segmented_control(
        "Kiểu",
        ["line", "bar", "area"],
        default="line",
        format_func={"line": "Đường", "bar": "Cột", "area": "Vùng"}.get,
        key="detail_kind",
    )
    or "line"
)
ui.chart_from_view(
    {
        "title": ind.name,
        "codes": [code],
        "range": rng,
        "transform": how,
        "kind": kind,
        "show_target": True,
        "show_bands": True,
        **_forward_line(code),
    },
    key="detail_chart",
)
ui.stats_table([code])
if code in ("fed_upper", "fed_lower"):
    from macro_app.ui import scorecard_view

    st.markdown("#### Kỳ vọng thị trường (FedWatch)")
    st.html(scorecard_view.fed_path_html(data.fed_path(), float(latest.loc["fed_upper", "value"])))
with st.expander("Ngưỡng của chỉ số này", expanded=False):
    threshold_form.render(code, key="detail_thr", editable=sidebar.is_admin())
ui.download_series_button([code], key="detail_dl")

flags = [f for f in str(rec["flags"]).split(";") if f in FLAG_LABEL]
if flags:
    st.markdown("**Lưu ý dữ liệu**")
    for f in flags:
        st.caption(f"• {FLAG_LABEL[f]}")
st.caption(f"Nguồn: {ind.source}" + (f" ({ind.source_url})" if ind.source_url else ""))
ui.footer()
