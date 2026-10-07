"""Bảng sửa ngưỡng dùng chung (trang Ngưỡng và tab Tác động BĐS)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from macro_app import fmt
from macro_app.config import load_thresholds
from macro_app.metrics.status import (
    LEVELS,
    WINDOW_METHODS,
    cuts_of,
    resolve_threshold,
    validate_cfg,
)
from macro_app.ui import data

METHOD_LABEL = {
    "zscore": "Z-score N năm",
    "percentile": "Phân vị N năm",
    "median_dev": "Lệch median N năm",
    "absolute": "Ngưỡng cứng",
    "target_band": "Lệch mục tiêu CP",
}
SIDE_LABEL = {
    "below": "Tăng là tốt",
    "above": "Tăng là không tốt",
    "both": "Ở giữa là tốt",
    "middle": "Ở giữa là không tốt",
}
METHOD_OF = {v: k for k, v in METHOD_LABEL.items()}
SIDE_OF = {v: k for k, v in SIDE_LABEL.items()}
EDIT_COLS = ["Kiểu ngưỡng", "N năm", "Số mức", "Các mốc", "Chiều", "Mô tả"]
HELP_CUTS = (
    "Mốc tăng dần, cách nhau bằng ;. Số mốc = số mức − 1. "
    "Z-score, lệch median, lệch mục tiêu: độ lệch dương (vd 1; 2). "
    "Phân vị: vd 50; 75; 90, chiều 'ở giữa' nhập khoảng cách tới P50 (vd 25; 40). "
    "Ngưỡng cứng: giá trị (vd 3,5; 4; 4,5)."
)


def cuts_text(cuts: list[float] | None) -> str:
    return "; ".join(fmt.number(c, 2).rstrip("0").rstrip(",") for c in cuts) if cuts else ""


def parse_cuts(text) -> list[float] | None:
    if text is None or (isinstance(text, float) and pd.isna(text)) or not str(text).strip():
        return None
    parts = [p.strip() for p in str(text).split(";") if p.strip()]
    return [float(p.replace(".", "").replace(",", ".")) if "," in p else float(p) for p in parts]


def current_cfg(code: str) -> dict:
    default, overrides = load_thresholds()
    cfg, _ = resolve_threshold(code, default, overrides)
    return cfg


def _data_info(code: str, method: str, years) -> dict:
    s = data.series(code).dropna()
    if s.empty:
        return {"Dữ liệu từ": "", "Số điểm": None, "Số điểm trong N năm": None}
    freq = data.catalog_map()[code].frequency
    n_window = None
    if method in WINDOW_METHODS and years and not pd.isna(years):
        n_window = int((s.index > s.index[-1] - pd.DateOffset(years=int(years))).sum())
    return {
        "Dữ liệu từ": fmt.period(s.index[0], freq),
        "Số điểm": len(s),
        "Số điểm trong N năm": n_window,
    }


def row_for(code: str) -> dict:
    cfg = current_cfg(code)
    cuts = cuts_of(cfg)
    method = cfg.get("method")
    years = cfg.get("window_years") if method in WINDOW_METHODS else None
    return {
        "Kiểu ngưỡng": METHOD_LABEL.get(method, method),
        "N năm": years,
        "Số mức": len(cuts) + 1 if cuts else None,
        "Các mốc": cuts_text(cuts),
        "Chiều": SIDE_LABEL.get(cfg.get("side", "both")),
        "Mô tả": cfg.get("description", ""),
        **_data_info(code, method, years),
    }


def column_config(names: list[str]) -> dict:
    return {
        "Chỉ số": st.column_config.SelectboxColumn(options=names, required=True, width="large"),
        "Kiểu ngưỡng": st.column_config.SelectboxColumn(
            options=list(METHOD_LABEL.values()), required=True
        ),
        "N năm": st.column_config.NumberColumn(
            min_value=1, max_value=30, step=1, help="Dùng cho z-score, phân vị, lệch median"
        ),
        "Số mức": st.column_config.SelectboxColumn(options=sorted(LEVELS), required=True),
        "Các mốc": st.column_config.TextColumn(help=HELP_CUTS),
        "Chiều": st.column_config.SelectboxColumn(options=list(SIDE_LABEL.values()), required=True),
        "Mô tả": st.column_config.TextColumn(width="medium"),
        "Dữ liệu từ": st.column_config.TextColumn(disabled=True),
        "Số điểm": st.column_config.NumberColumn(disabled=True),
        "Số điểm trong N năm": st.column_config.NumberColumn(disabled=True),
    }


def cfg_from_row(rec: dict) -> tuple[dict, list[str]]:
    name = rec.get("Chỉ số", "")
    try:
        cuts = parse_cuts(rec.get("Các mốc"))
    except ValueError:
        return {}, [f"{name}: mốc không phải số"]
    method = METHOD_OF.get(rec.get("Kiểu ngưỡng"))
    cfg = {
        "method": method,
        "cuts": cuts,
        "side": SIDE_OF.get(rec.get("Chiều"), "both"),
        "description": (rec.get("Mô tả") or "").strip()
        if isinstance(rec.get("Mô tả"), str)
        else "",
    }
    if method in WINDOW_METHODS:
        cfg["window_years"] = None if pd.isna(rec.get("N năm")) else int(rec["N năm"])
    errors = [f"{name}: {e}" for e in validate_cfg(cfg)]
    levels = rec.get("Số mức")
    if cuts and levels and not pd.isna(levels) and len(cuts) + 1 != int(levels):
        errors.append(f"{name}: {int(levels)} mức cần {int(levels) - 1} mốc, đang có {len(cuts)}")
    return cfg, errors


def changes(edited: pd.DataFrame, code_of: dict) -> tuple[list[tuple[str, dict, dict]], list[str]]:
    """Trả [(mã, cấu hình mới, cấu hình cũ)] cho các dòng đã sửa, và danh sách lỗi."""
    out, errors = [], []
    for rec in edited.dropna(subset=["Chỉ số"]).to_dict("records"):
        code = code_of.get(rec["Chỉ số"])
        if not code:
            continue
        before = row_for(code)
        blank = all(_same(rec.get(k), None) for k in EDIT_COLS)
        if blank or all(_same(rec.get(k), before.get(k)) for k in EDIT_COLS):
            continue
        cfg, errs = cfg_from_row(rec)
        if errs:
            errors += errs
            continue
        if cfg.get("description") == load_thresholds()[0].get("description"):
            cfg["description"] = ""  # không chép mô tả của ngưỡng mặc định
        out.append((code, cfg, current_cfg(code)))
    return out, errors


def _same(a, b) -> bool:
    a_na = a is None or (isinstance(a, float) and pd.isna(a)) or a == ""
    b_na = b is None or (isinstance(b, float) and pd.isna(b)) or b == ""
    if a_na or b_na:
        return a_na and b_na
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)
