"""Form ngưỡng của một chỉ số: tự lưu khi thay đổi hợp lệ, nút về ngưỡng mặc định."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from macro_app import admin
from macro_app.build import rescore
from macro_app.config import load_thresholds
from macro_app.metrics.status import DEFAULT_LABELS, WINDOW_METHODS, cuts_of
from macro_app.ui import data, rule_editor
from macro_app.ui.threshold_editor import current_cfg


def render(  # noqa: PLR0913
    code: str,
    *,
    key: str,
    editable: bool,
    cfg_now: dict | None = None,
    on_save: Callable[[dict], None] | None = None,
    with_scores: bool = False,
    recompute: bool = True,
) -> None:
    """Mặc định lưu vào ngưỡng chung; `on_save` để lưu nơi khác.

    `recompute=False`: gọi `on_save` rồi vẽ lại, không tính lại dữ liệu.
    """
    if data.series(code).dropna().empty:
        st.info("Chỉ số chưa có dữ liệu.")
        return
    global_mode = cfg_now is None
    cfg_now = current_cfg(code) if global_mode else cfg_now
    prefix = f"{key}_{code}"
    _sync_with_disk(prefix, cfg_now)
    shown = _shown_cfg(cfg_now)
    new = rule_editor.edit(code, shown, key=prefix, with_scores=with_scores, disabled=not editable)
    if not editable:
        st.caption("Chế độ xem. Sửa khi chạy với APP_MODE=admin.")
        return
    if new is not None and changed(new, cfg_now):
        if on_save:
            on_save(new)
        else:
            admin.save_threshold(code, new, cfg_now, st.session_state.get("admin_name", ""))
        if not recompute:
            st.rerun()
        _rebuild("Đã lưu và áp dụng")
    if recompute:
        st.caption("Tự lưu và áp dụng khi thay đổi hợp lệ.")
    if global_mode and st.button("Về ngưỡng mặc định", key=f"{prefix}_reset"):
        admin.reset_threshold(code, cfg_now, st.session_state.get("admin_name", ""))
        for k in [k for k in st.session_state if str(k).startswith(prefix)]:
            del st.session_state[k]  # tránh ô cũ tự lưu đè lại
        _rebuild("Đã về ngưỡng mặc định")


def _shown_cfg(cfg: dict) -> dict:
    """Ẩn mô tả mặc định của file ngưỡng khỏi ô mô tả."""
    default_desc = load_thresholds()[0].get("description")
    desc = cfg.get("description", "")
    return {**cfg, "description": "" if desc == default_desc else desc}


def _sync_with_disk(prefix: str, cfg_now: dict) -> None:
    """Cấu hình đổi ở nơi khác thì nạp lại ô nhập, tránh ô cũ tự lưu đè lên."""
    base_key = f"{prefix}__base"
    on_disk = repr(sorted(admin._clean_cfg(cfg_now).items())) + repr(cfg_now.get("scores"))
    if st.session_state.get(base_key) not in (None, on_disk):
        for k in [k for k in st.session_state if str(k).startswith(prefix) and k != base_key]:
            del st.session_state[k]
    st.session_state[base_key] = on_disk


def changed(new: dict, old: dict) -> bool:
    """So cấu hình form với bản đang lưu, bỏ qua khác biệt chỉ do giá trị mặc định."""
    from macro_app.metrics.scorecard import load_settings

    default_desc = load_thresholds()[0].get("description")
    defaults = load_settings()["default_scores"]

    def norm(cfg: dict) -> dict:
        clean = admin._clean_cfg(cfg)
        if clean.get("description") in ("", None, default_desc):
            clean.pop("description", None)
        if clean.get("method") not in WINDOW_METHODS:
            clean.pop("window_years", None)
        n = len(cuts_of(cfg) or []) + 1
        if clean.get("labels") == list(DEFAULT_LABELS.get(n, [])):
            clean.pop("labels", None)
        if (clean.get("measure") or {}).get("kind", "level") == "level":
            clean.pop("measure", None)
        scores = [float(x) for x in cfg.get("scores") or []]
        if scores and scores != [float(x) for x in defaults.get(n, [])]:
            clean["scores"] = scores
        return clean

    return norm(new) != norm(old)


def _rebuild(msg: str) -> None:
    with st.spinner("Đang tính lại…"):
        rescore()
    st.cache_data.clear()
    st.toast(msg)
    st.rerun()
