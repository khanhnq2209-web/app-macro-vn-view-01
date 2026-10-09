"""Tùy chỉnh hiển thị: khối, chart, lưu view, xuất/nhập YAML.

Bản công khai chỉ giữ view trong phiên. Quản trị lưu view dùng chung vào config/views.d/.
"""

import copy

import pandas as pd
import streamlit as st

from macro_app import views
from macro_app.charts.series import RANGE_YEARS, TRANSFORM_LABEL
from macro_app.ui import components as ui
from macro_app.ui import data, sidebar

st.title("Tùy chỉnh hiển thị")
st.caption("Chỉ đổi cách hiển thị, không đổi công thức, ngưỡng hay quy tắc tác động.")
catalog = data.catalog_map()
names = {c: f"{i.group} · {i.name}" for c, i in catalog.items()}
known = set(catalog)

if "edit_view" not in st.session_state:
    st.session_state["edit_view"] = copy.deepcopy(sidebar.current_view())
view = st.session_state["edit_view"]

top1, top2, top3 = st.columns([2, 1, 1])
new_name = top1.text_input("Tên view", value=view.get("name", ""), key="ve_name")
if top2.button("Bắt đầu từ view đang dùng", key="ve_reload"):
    st.session_state["edit_view"] = copy.deepcopy(sidebar.current_view())
    st.rerun()
if top3.button("Khôi phục mẫu", key="ve_reset"):
    st.session_state["edit_view"] = views.load_default()
    st.session_state["custom_view"] = None
    st.session_state["view_name"] = views.DEFAULT_NAME
    st.rerun()

tab_ov, tab_intl, tab_vn, tab_io = st.tabs(
    ["Tổng quan", "Quốc tế", "Việt Nam", "Lưu · Xuất/Nhập YAML"]
)

with tab_ov:
    st.caption("Thứ tự chọn là thứ tự hiển thị.")
    blocks = view.setdefault("overview", {}).setdefault("blocks", [])
    for i, block in enumerate(blocks):
        with st.container(border=True):
            block["title"] = st.text_input("Tên khối", block.get("title", ""), key=f"ve_bt_{i}")
            block["codes"] = st.multiselect(
                "Chỉ số",
                list(catalog),
                default=[c for c in block.get("codes", []) if c in known],
                format_func=names.get,
                key=f"ve_bc_{i}",
            )
            if st.button("Xóa khối", key=f"ve_bdel_{i}"):
                blocks.pop(i)
                st.rerun()
    if st.button("+ Thêm khối", key="ve_badd"):
        blocks.append({"title": "KHỐI MỚI", "codes": []})
        st.rerun()


def chart_editor(page: str, section: str) -> None:
    charts = view.setdefault(page, {}).setdefault(section, [])
    for i, chart in enumerate(charts):
        with st.expander(
            f"{chart.get('group', '')} · {chart.get('title', 'Chart')}", expanded=False
        ):
            k = f"ve_{page}_{section}_{i}"
            chart["title"] = st.text_input("Tiêu đề", chart.get("title", ""), key=f"{k}_t")
            if section == "charts":
                chart["group"] = st.text_input("Nhóm (A1…E1)", chart.get("group", ""), key=f"{k}_g")
            chart["codes"] = st.multiselect(
                "Chỉ số",
                list(catalog),
                default=[c for c in chart.get("codes", []) if c in known],
                format_func=names.get,
                key=f"{k}_c",
            )
            c1, c2, c3 = st.columns(3)
            chart["kind"] = c1.selectbox(
                "Kiểu",
                ["line", "bar", "area"],
                index=["line", "bar", "area"].index(chart.get("kind", "line")),
                format_func={"line": "Đường", "bar": "Cột", "area": "Vùng"}.get,
                key=f"{k}_k",
            )
            rngs = list(RANGE_YEARS)
            chart["range"] = c2.selectbox(
                "Khoảng mặc định", rngs, index=rngs.index(chart.get("range", "5Y")), key=f"{k}_r"
            )
            tfs = list(TRANSFORM_LABEL)
            chart["transform"] = c3.selectbox(
                "Biến đổi",
                tfs,
                index=tfs.index(chart.get("transform", "level")),
                format_func=TRANSFORM_LABEL.get,
                key=f"{k}_x",
            )
            chart["show_target"] = st.checkbox(
                "Đường mục tiêu", chart.get("show_target", False), key=f"{k}_st"
            )
            chart.pop("show_bands", None)
            chart["secondary"] = st.multiselect(
                "Vẽ trục phụ (bên phải)",
                chart["codes"],
                default=[c for c in chart.get("secondary", []) if c in chart["codes"]],
                format_func=names.get,
                key=f"{k}_sec",
            )
            chart["note"] = st.text_input("Chú thích", chart.get("note", ""), key=f"{k}_n")
            m1, m2, m3 = st.columns(3)
            if m1.button("↑ Lên", key=f"{k}_up") and i > 0:
                charts[i - 1], charts[i] = charts[i], charts[i - 1]
                st.rerun()
            if m2.button("↓ Xuống", key=f"{k}_down") and i < len(charts) - 1:
                charts[i + 1], charts[i] = charts[i], charts[i + 1]
                st.rerun()
            if m3.button("Xóa chart", key=f"{k}_del"):
                charts.pop(i)
                st.rerun()
    if st.button("+ Thêm chart", key=f"ve_{page}_{section}_add"):
        charts.append(
            {
                "group": "",
                "title": "Chart mới",
                "codes": [],
                "kind": "line",
                "range": "5Y",
                "transform": "level",
            }
        )
        st.rerun()


with tab_intl:
    chart_editor("international", "charts")
with tab_vn:
    st.markdown("**Theo nhóm**")
    chart_editor("vietnam", "charts")
    st.markdown("**Dẫn xuất**")
    chart_editor("vietnam", "derived")

with tab_io:
    view["name"] = new_name.strip()
    errors = views.validate(view, known)
    if errors:
        st.error("\n".join(errors))
    c1, c2 = st.columns(2)
    if c1.button("Áp dụng cho phiên này", type="primary", disabled=bool(errors), key="ve_apply"):
        if view["name"] == views.DEFAULT_NAME:
            st.error("Đặt tên khác 'Mặc định' để áp dụng view tùy chỉnh.")
        else:
            st.session_state["custom_view"] = copy.deepcopy(view)
            st.session_state["view_name"] = view["name"]
            st.toast(f"Đang dùng view '{view['name']}'")
    if sidebar.is_admin():
        if c2.button("Lưu view dùng chung (server)", disabled=bool(errors), key="ve_save"):
            try:
                path = views.save_shared(copy.deepcopy(view))
                st.session_state["view_name"] = view["name"]
                st.session_state["custom_view"] = None
                st.success(f"Đã lưu {path.name}")
            except ValueError as exc:
                st.error(str(exc))
        shared = list(views.list_shared())
        if shared:
            gone = st.selectbox("Xóa view dùng chung", ["—", *shared], key="ve_del_pick")
            if gone != "—" and st.button("Xóa", key="ve_del"):
                views.delete_shared(gone)
                st.rerun()
    else:
        c2.caption("View chỉ giữ trong phiên. Tải YAML để lưu lại.")
    st.download_button(
        "Xuất YAML",
        views.to_yaml(view).encode("utf-8"),
        file_name=f"view_{view['name'] or 'tuy_chinh'}.yaml",
        mime="text/yaml",
        key="ve_export",
    )
    uploaded = st.file_uploader("Nhập YAML", type=["yaml", "yml"], key="ve_import")
    if uploaded is not None and st.button("Nạp view từ file", key="ve_import_btn"):
        try:
            loaded = views.from_yaml(uploaded.getvalue().decode("utf-8"))
            bad = views.validate(loaded, known)
            if bad:
                st.error("\n".join(bad))
            else:
                st.session_state["edit_view"] = loaded
                st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    with st.expander("Xem YAML hiện tại"):
        st.code(views.to_yaml(view), language="yaml")
    st.dataframe(
        pd.DataFrame({"Chỉ số trong catalog": [names[c] for c in catalog]}),
        hide_index=True,
        height=200,
    )
ui.footer()
