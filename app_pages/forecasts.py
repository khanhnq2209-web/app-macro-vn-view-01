"""Kế hoạch & dự báo: bản đồ chỉ số thực tế → mục tiêu Chính phủ / FedWatch / chỉ số khác / nhập tay.

Chỉ để tham khảo (cột Kế hoạch / Dự báo ở trang Scorecard), không vào điểm.
Quản trị sửa bảng rồi bấm Lưu (ghi config/forecast_map.yaml).
"""

import pandas as pd
import streamlit as st

from macro_app import admin
from macro_app.config import load_targets
from macro_app.metrics import forward as fw
from macro_app.ui import components as ui
from macro_app.ui import data, scorecard_view, sidebar

st.title("Kế hoạch & dự báo")
st.caption(
    "Mỗi dòng gắn một chỉ số thực tế với kế hoạch hoặc dự báo của nó. Trang Scorecard hiện số này "
    "ở cột Kế hoạch / Dự báo để tham khảo, không tính vào điểm."
)
mappings = fw.load_forecast_map()
catalog = data.catalog_map()
st.html(scorecard_view.forecast_map_html(data.forecast_overview(mappings)))

with st.expander("Đường lãi suất Fed kỳ vọng (FedWatch)"):
    lat = data.latest().set_index("code")
    upper = lat.loc["fed_upper", "value"] if "fed_upper" in lat.index else float("nan")
    st.html(scorecard_view.fed_path_html(data.fed_path(), upper))

if not sidebar.is_admin():
    ui.footer()
    st.stop()

# ---------------- Sửa bản đồ (quản trị) ----------------
st.divider()
st.markdown("#### Sửa bản đồ")
st.caption(
    "Chọn chỉ số thực tế và nguồn kế hoạch / dự báo. Chọn 'Nhập tay' để tự gõ số (vd mục tiêu "
    "nội bộ, dự báo IMF): điền Giá trị và Kỳ (2026 hoặc 12/2026). Bấm Lưu để áp dụng."
)
targets = load_targets()
source_opts: dict[str, tuple[str, str]] = {}
for tid, t in targets.items():
    source_opts[f"Mục tiêu CP · {t.get('name', tid)}"] = ("target", tid)
for ref, text in (("upper", "biên trên"), ("lower", "biên dưới"), ("effective", "lãi hiệu dụng")):
    source_opts[f"FedWatch · {text} kỳ vọng"] = ("fedwatch", ref)
for code, ind in sorted(catalog.items(), key=lambda kv: kv[1].name):
    source_opts[f"Chỉ số · {ind.name}"] = ("indicator", code)
MANUAL = "Nhập tay"
source_opts[MANUAL] = ("manual", "")
option_of = {v: k for k, v in source_opts.items()}
name_of = {c: i.name for c, i in catalog.items()}
code_of = {v: k for k, v in name_of.items()}

table = pd.DataFrame(
    [
        {
            "Chỉ số thực tế": name_of.get(m.get("code"), m.get("code")),
            "Nguồn kế hoạch / dự báo": option_of.get((m.get("kind"), m.get("ref") or ""), MANUAL),
            "Giá trị (nhập tay)": float(m["value"]) if m.get("value") is not None else float("nan"),
            "Kỳ (nhập tay)": str(m.get("period") or ""),
            "Nhãn": m.get("label") or "",
            "Ghi chú": m.get("note") or "",
        }
        for m in mappings
    ],
    columns=[
        "Chỉ số thực tế",
        "Nguồn kế hoạch / dự báo",
        "Giá trị (nhập tay)",
        "Kỳ (nhập tay)",
        "Nhãn",
        "Ghi chú",
    ],
)
edited = st.data_editor(
    table,
    num_rows="dynamic",
    hide_index=True,
    width="stretch",
    key=f"fmap_editor_{st.session_state.setdefault('fmap_ver', 0)}",
    column_config={
        "Chỉ số thực tế": st.column_config.SelectboxColumn(
            options=sorted(name_of.values()), required=True, width="medium"
        ),
        "Nguồn kế hoạch / dự báo": st.column_config.SelectboxColumn(
            options=list(source_opts), required=True, width="medium"
        ),
        "Giá trị (nhập tay)": st.column_config.NumberColumn(help="Chỉ dùng khi nguồn là Nhập tay"),
        "Kỳ (nhập tay)": st.column_config.TextColumn(help="2026 (cả năm) hoặc 12/2026 (tháng)"),
        "Nhãn": st.column_config.TextColumn(help="Tên ngắn hiện trên bảng, vd Mục tiêu CP, IMF"),
        "Ghi chú": st.column_config.TextColumn(width="large"),
    },
)
new_maps = []
for rec in edited.dropna(subset=["Chỉ số thực tế", "Nguồn kế hoạch / dự báo"]).to_dict("records"):
    kind, ref = source_opts[rec["Nguồn kế hoạch / dự báo"]]
    value = rec.get("Giá trị (nhập tay)")
    new_maps.append(
        {
            "code": code_of.get(rec["Chỉ số thực tế"]),
            "kind": kind,
            "ref": ref or None,
            "value": None if kind != "manual" or pd.isna(value) else float(value),
            "period": (str(rec.get("Kỳ (nhập tay)") or "").strip() or None)
            if kind == "manual"
            else None,
            "label": (rec.get("Nhãn") or "").strip() or None,
            "note": (rec.get("Ghi chú") or "").strip() or None,
        }
    )
errors = [e for m in new_maps for e in fw.validate_mapping(m, catalog, set(targets))]
c1, c2 = st.columns([1, 4])
if errors:
    c2.error(" · ".join(errors))
if c1.button("Lưu", type="primary", disabled=bool(errors), key="fmap_save", width="stretch"):
    admin.save_forecast_map(new_maps)
    st.session_state["fmap_ver"] += 1
    st.cache_data.clear()
    st.toast(f"Đã lưu {len(new_maps)} dòng")
    st.rerun()
ui.footer()
