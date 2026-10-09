"""Cổng sửa cấu hình scorecard: một mật khẩu chung `CONFIG_PASSWORD` + tên người sửa.

Quản trị local (APP_MODE=admin) vào thẳng. Đếm lần nhập sai và lần lưu ở phía máy chủ (dùng chung
mọi phiên, theo IP nếu biết), nên tải lại trang không né được: sai 5 lần trong 10 phút thì khóa
5 phút; tối đa 30 lần lưu mỗi giờ.
"""

from __future__ import annotations

import hmac
import time

import streamlit as st

from macro_app.ui import sidebar

MAX_FAILS = 5
FAIL_WINDOW = 600
LOCK_SECONDS = 300
MAX_SAVES_PER_HOUR = 30


@st.cache_resource(show_spinner=False)
def _counters() -> dict[str, dict[str, list[float]]]:
    """Bộ đếm dùng chung mọi phiên: {"fails"|"saves"|"locks": {khách: [thời điểm]}}."""
    return {"fails": {}, "saves": {}, "locks": {}}


def _who() -> str:
    """IP người dùng nếu Streamlit biết (chuỗi thật), không thì đếm chung một nhóm."""
    try:
        ip = st.context.ip_address
    except AttributeError:
        ip = None
    return ip if isinstance(ip, str) and ip else "all"


def _recent(kind: str, seconds: float) -> list[float]:
    now = time.time()
    keep = [t for t in _counters()[kind].get(_who(), []) if now - t < seconds]
    _counters()[kind][_who()] = keep
    return keep


def editor() -> str | None:
    ss = st.session_state
    if sidebar.is_admin():
        return ss.get("admin_name") or "quản trị"
    return ss.get("editor_name")


def lock() -> None:
    st.session_state.pop("editor_name", None)


def _check(name: str, typed: str, password: str) -> None:
    if name.strip() and hmac.compare_digest(typed.encode(), password.encode()):
        st.session_state["editor_name"] = name.strip()[:60]
        _counters()["fails"][_who()] = []
        st.rerun()
    fails = _recent("fails", FAIL_WINDOW)
    fails.append(time.time())
    if len(fails) >= MAX_FAILS:
        _counters()["locks"][_who()] = [time.time() + LOCK_SECONDS]
        _counters()["fails"][_who()] = []
    st.error("Sai mật khẩu hoặc chưa nhập tên.")


def gate() -> str | None:
    """Tên người sửa nếu đã mở khóa; chưa thì vẽ form nhập mật khẩu và trả None."""
    name = editor()
    if name:
        return name
    password = sidebar.secret("CONFIG_PASSWORD")
    if not password:
        st.info("Bản này chưa bật sửa cấu hình (thiếu CONFIG_PASSWORD trong Secrets).")
        return None
    wait = max(_counters()["locks"].get(_who(), [0])) - time.time()
    if wait > 0:
        st.error(f"Nhập sai nhiều lần. Thử lại sau {int(wait // 60) + 1} phút.")
        return None
    with st.form("cfg_gate", border=True):
        st.markdown("**Nhập mật khẩu để sửa cấu hình scorecard**")
        who = st.text_input("Tên của bạn (ghi vào lịch sử thay đổi)", key="gate_name")
        typed = st.text_input("Mật khẩu", type="password", key="gate_pw")
        submitted = st.form_submit_button("Mở khóa", type="primary")
    if submitted:
        _check(who, typed, password)
    return None


def save_allowed() -> bool:
    return len(_recent("saves", 3600)) < MAX_SAVES_PER_HOUR


def note_save() -> None:
    _recent("saves", 3600).append(time.time())


def reset_counters() -> None:
    """Cho test: xóa bộ đếm dùng chung."""
    _counters.clear()
