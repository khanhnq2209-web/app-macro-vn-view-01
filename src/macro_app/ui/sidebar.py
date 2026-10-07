"""Sidebar và state chung: quyền quản trị, chế độ trình bày, chọn view, cập nhật dữ liệu."""

from __future__ import annotations

import hmac
import os

import streamlit as st
from dotenv import load_dotenv

from macro_app import views
from macro_app.paths import PUBLIC_DIR, ROOT
from macro_app.ui import data

load_dotenv(ROOT / ".env")


def _secret(name: str) -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except FileNotFoundError:
        pass
    return os.getenv(name, "")


def admin_allowed() -> bool:
    """Cần APP_MODE=admin và ADMIN_PASSWORD. Mặc định đóng."""
    return _secret("APP_MODE").lower() == "admin" and bool(_secret("ADMIN_PASSWORD"))


def auto_admin() -> bool:
    """APP_MODE=admin mà không đặt mật khẩu thì vào thẳng quản trị."""
    return _secret("APP_MODE").lower() == "admin" and not _secret("ADMIN_PASSWORD")


def is_admin() -> bool:
    return bool(st.session_state.get("is_admin"))


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("is_admin", auto_admin())
    ss.setdefault("admin_name", "local" if auto_admin() else "")
    ss.setdefault("detail_code", None)
    ss.setdefault("view_name", views.DEFAULT_NAME)
    ss.setdefault("custom_view", None)
    ss["public_mode"] = not ss["is_admin"]


def presentation_mode() -> bool:
    return st.query_params.get("present") == "1"


def set_presentation(on: bool) -> None:
    if on:
        st.query_params["present"] = "1"
    elif "present" in st.query_params:
        del st.query_params["present"]


def current_view() -> dict:
    ss = st.session_state
    if ss.get("custom_view") is not None and ss["view_name"] == ss["custom_view"].get("name"):
        return ss["custom_view"]
    shared = views.list_shared()
    if ss["view_name"] in shared:
        return shared[ss["view_name"]]
    return views.load_default()


def _view_picker() -> None:
    names = [views.DEFAULT_NAME, *views.list_shared()]
    custom = st.session_state.get("custom_view")
    if custom is not None and custom.get("name") not in names:
        names.append(custom["name"])
    if st.session_state["view_name"] not in names:
        st.session_state["view_name"] = views.DEFAULT_NAME
    st.selectbox("View hiển thị", names, key="view_name")


def _login() -> None:
    if not admin_allowed():
        return
    if is_admin():
        st.success(f"Quản trị: {st.session_state['admin_name'] or 'admin'}")
        if st.button("Đăng xuất", key="logout"):
            st.session_state["is_admin"] = False
            st.rerun()
        return
    with st.expander("Đăng nhập quản trị"), st.form("login", border=False):
        name = st.text_input("Tên (ghi vào lịch sử)")
        pw = st.text_input("Mật khẩu", type="password")
        if st.form_submit_button("Đăng nhập"):
            if hmac.compare_digest(pw, _secret("ADMIN_PASSWORD")) and name.strip():
                st.session_state["is_admin"] = True
                st.session_state["admin_name"] = name.strip()
                st.rerun()
            else:
                st.error("Sai mật khẩu hoặc thiếu tên")


def _refresh_panel() -> None:
    from macro_app import admin
    from macro_app.build import run_build

    with st.expander("Cập nhật dữ liệu", expanded=False):
        sources = st.multiselect(
            "Nguồn",
            list(admin.SOURCE_LABEL),
            default=["fred", "yahoo", "fedwatch", "lme"],
            format_func=admin.SOURCE_LABEL.get,
            key="refresh_sources",
        )
        if st.button("Refresh dữ liệu", type="primary", key="refresh_btn", disabled=not sources):
            bar = st.progress(0.0, text="Bắt đầu…")
            results = admin.refresh_sources(
                sources,
                progress=lambda n, i, total: bar.progress(
                    i / (total + 1), text=f"Đang tải {admin.SOURCE_LABEL[n]}…"
                ),
            )
            bar.progress(1.0, text="Tính lại trạng thái…")
            run_build()
            st.cache_data.clear()
            st.session_state["refresh_results"] = results
            st.rerun()
        if st.button("Gộp file trong data/inbox", key="merge_btn"):
            report = admin.merge_inbox()
            run_build()
            st.cache_data.clear()
            st.session_state["merge_report"] = report
            st.rerun()
        if st.session_state.get("refresh_results"):
            for name, res in st.session_state["refresh_results"].items():
                (st.success if res == "ok" else st.error)(
                    f"{admin.SOURCE_LABEL.get(name, name)}: {res}"
                )
        if st.session_state.get("merge_report") is not None:
            st.caption(f"Gộp inbox: {len(st.session_state['merge_report'])} file")
            st.json(st.session_state["merge_report"], expanded=False)


def render() -> None:
    meta = data.build_meta()
    with st.sidebar:
        st.markdown("### Theo dõi vĩ mô")
        st.caption(f"Cập nhật {meta.get('built_at', '')[:16].replace('T', ' ')}")
        _view_picker()
        on = st.toggle("Chế độ trình bày", value=presentation_mode(), key="present_toggle")
        if on != presentation_mode():
            set_presentation(on)
            st.rerun()
        latest_csv = PUBLIC_DIR / "latest.csv"
        if latest_csv.exists():
            st.download_button(
                "Tải latest.csv", latest_csv.read_bytes(), "latest.csv", "text/csv", key="dl_latest"
            )
        repo = _secret("REPO_URL")
        if repo:
            st.markdown(f"[Repo dữ liệu]({repo})")
        _login()
        if is_admin():
            _refresh_panel()
        with st.expander("Ngày sửa cuối file raw VN"):
            for name, ts in (meta.get("raw_modified") or {}).items():
                st.caption(f"{name}: {ts}")
