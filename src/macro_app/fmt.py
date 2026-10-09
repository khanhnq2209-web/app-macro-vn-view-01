"""Định dạng số/kỳ kiểu Việt Nam; mọi con số hiển thị đi qua đây.

Ví dụ: 4,52%, 25.643, +25 bps, 15/08/2026, T8/2026, Q2/2026.
"""

from __future__ import annotations

import math

import pandas as pd

MISSING = "—"


def _is_missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x)) or pd.isna(x)


def number(x, decimals: int = 2) -> str:
    """Dấu chấm ngàn, dấu phẩy thập phân."""
    if _is_missing(x):
        return MISSING
    text = f"{float(x):,.{decimals}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def signed(x, decimals: int = 2) -> str:
    if _is_missing(x):
        return MISSING
    sign = "+" if x > 0 else ("−" if x < 0 else "±")
    return f"{sign}{number(abs(x), decimals)}"


def value(x, unit: str, decimals: int = 2) -> str:
    if _is_missing(x):
        return MISSING
    if unit == "%":
        return f"{number(x, decimals)}%"
    return f"{number(x, decimals)} {unit}".strip()


def change(x, change_unit: str) -> str:
    """bps: '+25 bps'; pp: '+0,25 điểm %'; pct: '+1,2%'."""
    if _is_missing(x):
        return MISSING
    if change_unit == "bps":
        return f"{signed(x, 0)} bps"
    if change_unit == "pp":
        return f"{signed(x, 2)} điểm %"
    return f"{signed(x, 1)}%"


def date(d) -> str:
    if _is_missing(d):
        return MISSING
    return pd.Timestamp(d).strftime("%d/%m/%Y")


def period(d, frequency: str) -> str:  # noqa: PLR0911
    """Kỳ theo tần suất: ngày/tuần dd/mm/yyyy, tháng T8/2026, quý Q2/2026, năm 2026."""
    if _is_missing(d):
        return MISSING
    ts = pd.Timestamp(d)
    if frequency == "M":
        return f"T{ts.month}/{ts.year}"
    if frequency == "Q":
        return f"Q{ts.quarter}/{ts.year}"
    if frequency == "A":
        return str(ts.year)
    return date(ts)


def prob(p) -> str:
    return MISSING if _is_missing(p) else f"{number(p * 100, 1)}%"


MD_SPECIAL = "\\`*_[]()<>#!~|$"  # tạo link, ảnh, định dạng; không thoát - . :


def md(text) -> str:
    """Chữ người dùng nhập đưa vào Markdown của Streamlit: thoát ký tự đặc biệt (link, ảnh...)."""
    return "".join(f"\\{c}" if c in MD_SPECIAL else c for c in str(text))
