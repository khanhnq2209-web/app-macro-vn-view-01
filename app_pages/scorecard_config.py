"""Cấu hình scorecard: nhập mật khẩu → danh sách bộ → 4 bước (thông tin, nhóm và tỷ trọng, mốc,
xem lại). Sửa trên bản nháp trong phiên; chỉ bấm Lưu mới ghi vào kho dùng chung (có lịch sử)."""

import streamlit as st

from macro_app import fmt
from macro_app.ui import components as ui
from macro_app.ui import config_steps as cfg
from macro_app.ui import data, editor_gate, profile_store

st.title("Cấu hình scorecard")
editor = editor_gate.gate()
if not editor:
    ui.footer()
    st.stop()

ss = st.session_state
store = profile_store.load()
saved_all = store["profiles"]
catalog = data.catalog_map()
if store["error"]:
    st.warning(store["error"])

head = st.columns([5, 1.2], vertical_alignment="center")
head[0].caption(f"Đang sửa với tên **{fmt.md(editor)}** · lưu vào {store['where']}")
if not editor_gate.sidebar.is_admin() and head[1].button(
    "Khóa lại", key="cfg_lock", width="stretch"
):
    editor_gate.lock()
    st.rerun()

target = ss.pop("cfg_target", None)  # từ nút ⚙ ở trang Scorecard
if target and target.get("profile") in saved_all:
    same = ss.get("cfg_bo") == target["profile"] and not ss.get("cfg_new")
    if not same and ss.get("cfg_draft") and cfg.is_dirty(saved_all):
        ss["cfg_pending"] = target
    else:
        if not same or not ss.get("cfg_draft"):
            slug = target["profile"]
            cfg.open_bo(slug, saved_all[slug], store["meta"].get(slug, {}).get("version", 0))
        ss.update(cfg_view="wiz", cfg_step=target["step"], cfg_seg=target["segment"])
        if target.get("code"):
            ss["cfg_sel"] = target["code"]

pending = ss.get("cfg_pending")
if pending:
    st.warning("Bạn đang có bản nháp chưa lưu của bộ khác. Mở bộ mới sẽ bỏ bản nháp đó.")
    c = st.columns(2)
    if c[0].button("Bỏ bản nháp và mở", key="cfg_pending_go"):
        slug = pending["profile"]
        cfg.open_bo(slug, saved_all[slug], store["meta"].get(slug, {}).get("version", 0))
        ss.update(cfg_step=pending["step"], cfg_seg=pending["segment"])
        if pending.get("code"):
            ss["cfg_sel"] = pending["code"]
        ss.pop("cfg_pending")
        st.rerun()
    if c[1].button("Giữ bản nháp", key="cfg_pending_keep"):
        ss.pop("cfg_pending")
        st.rerun()

if ss.get("cfg_view") != "wiz" or not ss.get("cfg_draft"):
    ss["cfg_view"] = "list"
    cfg.render_list(store, editor)
    ui.footer()
    st.stop()

draft = ss["cfg_draft"]
if not ss.get("cfg_new") and ss.get("cfg_bo") not in saved_all:  # bộ vừa bị người khác xóa
    st.error("Bộ đang sửa không còn trên kho (có thể vừa bị xóa). Lưu sẽ tạo lại bộ này.")
    ss["cfg_new"] = True
    ss["cfg_base"] = 0  # tạo lại bộ: không còn phiên bản để so

ctx = st.columns([1.3, 4, 1.3], vertical_alignment="center")
if ctx[0].button("← Danh sách bộ", key="cfg_tolist", width="stretch"):
    ss["cfg_view"] = "list"
    st.rerun()
status = "chưa lưu" if cfg.is_dirty(saved_all) else "đã lưu"
title = "Tạo mới" if ss.get("cfg_new") else "Đang sửa"
ctx[1].markdown(f"{title}: **{draft.get('name') or '(chưa đặt tên)'}** · :gray[{status}]")
if ctx[2].button(
    "Xem Scorecard", key="cfg_tosc", width="stretch", disabled=ss.get("cfg_new", False)
):
    ss["sc_profile"] = ss["cfg_bo"]
    st.switch_page("app_pages/scorecard.py")

results = cfg.checks(saved_all, catalog)
cfg.render_stepper(results)
step = ss.get("cfg_step", 1)
if step == 1:
    cfg.step_info(saved_all)
elif step == 2:
    cfg.step_groups(catalog)
elif step == 3:
    cfg.step_rules(catalog)
else:
    cfg.step_review(results, catalog)
results = cfg.checks(saved_all, catalog)  # bước vừa sửa bản nháp
cfg.render_bar(store, results, editor)
ui.footer()
