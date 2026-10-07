"""Cờ chất lượng dữ liệu cho từng chỉ số (icon + tooltip trên giao diện)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from macro_app.metrics.transforms import PERIOD_RULE, clean, yoy_pct, zscore_latest

FLAG_LABEL = {
    "stale": "Chưa có số mới (đã quá 2 kỳ)",
    "gaps": "Thiếu từ 2 kỳ liên tiếp trong 3 năm gần nhất",
    "anomaly": "Số mới nhất lệch bất thường (|z| > 4)",
    "repeated": "Có kỳ lặp y hệt kỳ trước trong 12 kỳ gần nhất, nghi lỗi nguồn",
    "unit_unverified": "Đơn vị chưa xác minh",
    "cumulative_ytd": "Số lũy kế từ đầu năm",
    "rebase_suspect": "Nghi đổi năm gốc, tăng trưởng không so sánh được",
    "default_threshold": "Đang dùng ngưỡng thống kê mặc định",
    "manual": "Nhập tay",
    "ai_suggested_confirmed": "AI gợi ý, đã xác nhận",
    "cache": "Dữ liệu từ cache",
    "vendor_hidden": "Số liệu có bản quyền, không hiển thị trên bản công khai",
}
FLAG_ICON = {
    "stale": "⏳",
    "gaps": "▢",
    "anomaly": "⚠",
    "repeated": "⧉",
    "unit_unverified": "❓",
    "cumulative_ytd": "Σ",
    "rebase_suspect": "⟲",
    "default_threshold": "≈",
    "manual": "✎",
    "ai_suggested_confirmed": "✎AI",
    "cache": "⛁",
    "vendor_hidden": "🔒",
}


def is_stale(series: pd.Series, frequency: str, today: pd.Timestamp, stale_days: dict) -> bool:
    s = clean(series)
    if s.empty:
        return False  # card đã hiện 'Chưa có dữ liệu', không gắn thêm cờ cũ
    return bool((today - s.index[-1]).days > stale_days[frequency])


def has_gaps(series: pd.Series, frequency: str, today: pd.Timestamp, params: dict) -> bool:
    if frequency not in PERIOD_RULE:
        return False  # chuỗi ngày/tuần: ngày nghỉ không phải thiếu kỳ
    s = clean(series)
    start = today - pd.DateOffset(years=params["gap_lookback_years"])
    s = s[s.index >= start]
    if s.empty:
        return False
    grid = s.resample(PERIOD_RULE[frequency]).last()
    missing = grid.isna().astype(int)
    runs = missing.groupby((missing != missing.shift()).cumsum()).transform("sum") * missing
    return bool(runs.max() >= params["gap_min_consecutive"])


def has_repeat(series: pd.Series, frequency: str, window: int = 12) -> bool:
    """Chuỗi tháng/quý có 2 kỳ liền nhau trùng y hệt trong `window` kỳ gần nhất."""
    if frequency not in ("M", "Q"):
        return False
    s = clean(series).tail(window)
    return bool(len(s) > 1 and (s.diff().iloc[1:] == 0).any())


def is_anomaly(series: pd.Series, threshold_z: float, min_points: int) -> bool:
    z = zscore_latest(series, 5, min_points)
    return bool(not np.isnan(z) and abs(z) > threshold_z)


def is_rebase_suspect(level_series: pd.Series, frequency: str, jump_pp: float) -> bool:
    """YoY kỳ mới nhất lệch > jump_pp so với TB YoY 12 kỳ trước."""
    yoy = yoy_pct(level_series, frequency).dropna()
    if len(yoy) < 13:
        return False
    return bool(abs(yoy.iloc[-1] - yoy.iloc[-13:-1].mean()) > jump_pp)


def quality_flags(  # noqa: PLR0913
    *,
    series: pd.Series,
    frequency: str,
    catalog_flags: tuple[str, ...],
    today: pd.Timestamp,
    params: dict,
    min_points: int,
    rebase_input: pd.Series | None = None,
) -> list[str]:
    flags = [f for f in catalog_flags if f in ("unit_unverified", "cumulative_ytd")]
    if is_stale(series, frequency, today, params["stale_days"]):
        flags.append("stale")
    if has_gaps(series, frequency, today, params):
        flags.append("gaps")
    if is_anomaly(series, params["anomaly_abs_z"], min_points):
        flags.append("anomaly")
    if "no_repeat_check" not in catalog_flags and has_repeat(series, frequency):
        flags.append("repeated")
    if (
        "check_rebase" in catalog_flags
        and rebase_input is not None
        and is_rebase_suspect(rebase_input, frequency, params["rebase_yoy_jump_pp"])
    ):
        flags.append("rebase_suspect")
    return flags
