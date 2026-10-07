"""Trang 5: ngưỡng. Bảng xem nhanh; chọn một dòng để mở form đặt ngưỡng có xem trước."""

import pandas as pd
import streamlit as st

from macro_app import admin, fmt
from macro_app.metrics.status import STATUS_LABEL
from macro_app.ui import components as ui
from macro_app.ui import data, sidebar, threshold_form, threshold_sets
from macro_app.ui import threshold_editor as te

st.title("Ngưỡng cảnh báo")
latest = data.latest()
catalog = data.catalog_map()
editable = sidebar.is_admin()

n_default = int((latest["threshold_source"] == "default").sum()) if not latest.empty else 0
if n_default:
    st.warning(
        f"{n_default}/{len(latest)} chỉ số đang dùng ngưỡng thống kê mặc định (z-score 1 và 2 trên 5 năm), "
        "chưa có ngưỡng nghiệp vụ. Bật một bộ ngưỡng bên dưới hoặc đặt riêng từng chỉ số."
    )

threshold_sets.render(editable=editable)
st.divider()

by_code = latest.set_index("code")
codes = [c for c in catalog if c in by_code.index]
rows = []
for code in codes:
    rec = by_code.loc[code]
    info = te.row_for(code)
    rows.append(
        {
            "Chỉ số": catalog[code].name,
            "Giá trị": fmt.value(rec["value"], rec["unit"], catalog[code].decimals),
            "Trạng thái": STATUS_LABEL.get(rec["status"], rec["status"]),
            "Kiểu ngưỡng": info["Kiểu ngưỡng"],
            "Chiều": info["Chiều"],
            "Các mốc": info["Các mốc"],
            "N năm": info["N năm"],
            "Mô tả": info["Mô tả"],
            "Dữ liệu từ": info["Dữ liệu từ"],
            "Số điểm": info["Số điểm"],
        }
    )
st.caption("Bấm vào một dòng để đặt ngưỡng cho chỉ số đó.")
overview = pd.DataFrame(rows)
for col in ("N năm", "Số điểm"):
    overview[col] = pd.to_numeric(overview[col], errors="coerce").astype("Int64")
picked = st.dataframe(
    overview,
    hide_index=True,
    width="stretch",
    height=380,
    on_select="rerun",
    selection_mode="single-row",
    key="thr_table",
)
selected = picked.selection.rows if picked and picked.selection else []
default_code = codes[selected[0]] if selected else st.session_state.get("thr_code", codes[0])
code = st.selectbox(
    "Chỉ số",
    codes,
    index=codes.index(default_code),
    format_func=lambda c: f"{catalog[c].group} · {catalog[c].name}",
    key=f"thr_pick_{default_code}",
)
st.session_state["thr_code"] = code
st.markdown(f"#### Đặt ngưỡng: {catalog[code].name}")
threshold_form.render(code, key="thr", editable=editable)

st.markdown("##### 10 thay đổi gần nhất")
hist = admin.threshold_history(10)
if hist.empty:
    st.caption("Chưa có thay đổi ngưỡng.")
else:
    names = {c: i.name for c, i in catalog.items()}
    hist = hist.assign(code=hist["code"].map(names).fillna(hist["code"]))
    hist.columns = ["Thời điểm", "Người sửa", "Chỉ số", "Cũ", "Mới"]
    st.dataframe(hist, hide_index=True, width="stretch")
ui.footer()
