"""Bộ cấu hình scorecard cho app: đọc từ kho dùng chung (Google Sheets khi deploy), cache ngắn.

Kho đọc lỗi thì dùng bản gốc YAML trong repo và báo một dòng (không in lỗi gốc: có thể kèm chi
tiết kết nối). Ghi xong thì xóa cache để mọi người thấy bản mới.
"""

from __future__ import annotations

import streamlit as st

from macro_app import config_store as cs
from macro_app import profiles as pf

READ_TTL = 30  # giây: người khác lưu thì tối đa sau chừng này thời gian sẽ thấy


def _secrets() -> dict:
    try:
        return st.secrets.to_dict()
    except FileNotFoundError:
        return {}


@st.cache_resource(show_spinner=False)
def store() -> cs.Store:
    return cs.make_store(_secrets())


@st.cache_data(ttl=READ_TTL, show_spinner=False)
def _rows() -> list[dict]:
    return store().rows()


def where() -> str:
    """Mô tả nơi lưu cho người sửa (không ném lỗi: kho dựng hỏng thì báo chưa nối được)."""
    try:
        kind = type(store()).__name__
    except Exception:  # cấu hình Sheet sai: không in lỗi gốc
        return "kho cấu hình (chưa kết nối được)"
    return {
        "SheetStore": "Google Sheets dùng chung",
        "FileStore": "file trên máy này (chưa nối Google Sheets)",
        "MemoryStore": "bộ nhớ tạm (test)",
    }.get(kind, kind)


def load() -> dict:
    """{profiles, meta, default, rows, error}: bộ hiện hành (YAML gốc đè bằng bản trên kho)."""
    seed = pf.load_profiles()
    error = ""
    try:
        rows = _rows()
    except Exception as exc:  # mạng, quyền, cấu hình
        rows = []
        error = (
            f"Không đọc được kho cấu hình ({type(exc).__name__}); đang hiển thị bản gốc trong repo."
        )
    loaded = cs.load_profiles(rows, seed)
    return {
        "profiles": loaded,
        "meta": cs.meta(rows),
        "default": cs.default_slug(rows, loaded, pf.default_profile()),
        "rows": rows,
        "error": error,
        "where": where(),
    }


def fresh_rows() -> list[dict]:
    """Đọc thẳng kho (không cache), dùng ngay trước khi ghi."""
    return store().rows()


def _done() -> None:
    _rows.clear()


def save(slug: str, profile: dict, *, base: int, by: str) -> int:
    try:
        return cs.save(store(), slug, profile, base=base, by=by)
    finally:
        _done()


def delete(slug: str, *, base: int, by: str) -> None:
    try:
        cs.delete(store(), slug, base=base, by=by)
    finally:
        _done()


def restore(slug: str, version: int, *, base: int, by: str) -> int:
    try:
        return cs.restore(store(), slug, version, base=base, by=by)
    finally:
        _done()


def set_default(slug: str, *, by: str) -> None:
    try:
        cs.set_default(store(), slug, by=by)
    finally:
        _done()
