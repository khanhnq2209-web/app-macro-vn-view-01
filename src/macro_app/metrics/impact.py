"""Hướng của biến + tác động tới BĐS (config/impact_rules.yaml)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from macro_app.metrics.transforms import clean, value_year_ago

UP, DOWN, FLAT, UNKNOWN = "up", "down", "flat", "unknown"
TREND_LABEL = {UP: "đang tăng", DOWN: "đang giảm", FLAT: "đi ngang", UNKNOWN: "chưa rõ"}
CELLS = ("housing_demand", "housing_supply", "industrial_demand", "industrial_supply")
FLIP = {"up": "down", "down": "up", "both": "both", "none": "none"}

FAVORABLE, UNFAVORABLE, TWO_WAY, NEUTRAL = "favorable", "unfavorable", "two_way", "neutral"
TAG_LABEL = {
    FAVORABLE: "▲ Thuận lợi",
    UNFAVORABLE: "▼ Bất lợi",
    TWO_WAY: "◆ Hai chiều",
    NEUTRAL: "● Trung tính",
}


def trend(series: pd.Series, frequency: str, params: dict) -> tuple[str, float]:
    """So giá trị mới nhất với TB N kỳ trước. Trả (hướng, chênh lệch)."""
    s = clean(series)
    lookback = int(params["lookback_periods"][frequency])
    if len(s) < lookback + 1:
        return UNKNOWN, np.nan
    latest = s.iloc[-1]
    base = s.iloc[-(lookback + 1) : -1].mean()
    delta = latest - base
    recent = s[s.index > s.index[-1] - pd.DateOffset(years=5)]
    step_std = recent.diff().std()
    band = params["flat_std_ratio"] * step_std * np.sqrt(lookback) if step_std else 0.0
    if np.isnan(delta):
        return UNKNOWN, np.nan
    if abs(delta) <= band:
        return FLAT, delta
    return (UP if delta > 0 else DOWN), delta


def trend_vs_last_year(series: pd.Series, frequency: str, params: dict) -> tuple[str, float]:
    """Hướng của chuỗi lũy kế từ đầu năm: so với cùng kỳ năm trước (tránh 'giảm' giả tháng 1)."""
    s = clean(series)
    if s.empty:
        return UNKNOWN, np.nan
    if frequency in ("D", "W"):
        diff = (s - value_year_ago(s)).dropna()
    else:
        grid = s.resample("ME" if frequency == "M" else "QE").last()
        diff = (grid - grid.shift(12 if frequency == "M" else 4)).dropna()
    if diff.empty or diff.index[-1] != s.index[-1]:
        return UNKNOWN, np.nan
    delta = diff.iloc[-1]
    recent = diff[diff.index > diff.index[-1] - pd.DateOffset(years=5)]
    band = params["flat_std_ratio"] * recent.std() if len(recent) > 1 else 0.0
    if abs(delta) <= band:
        return FLAT, delta
    return (UP if delta > 0 else DOWN), delta


def favorability(direction: str, trend_dir: str) -> str:
    """Tag thuận lợi/bất lợi/hai chiều, suy từ `direction` trong catalog và hướng hiện tại."""
    if direction == "two_way":
        return TWO_WAY
    if trend_dir not in (UP, DOWN):
        return NEUTRAL
    good_when_up = direction == "up_good"
    return FAVORABLE if (trend_dir == UP) == good_when_up else UNFAVORABLE


def apply_sign(trend_dir: str, sign: int) -> str:
    """Chỉ số ngược chiều khái niệm của nhóm (sign = -1) thì đảo hướng trước khi tra quy tắc."""
    if sign >= 0 or trend_dir not in (UP, DOWN):
        return trend_dir
    return DOWN if trend_dir == UP else UP


def group_cells(group_rule: dict | None, trend_dir: str) -> dict[str, str] | None:
    """Ô tác động của nhóm theo hướng hiện tại; đi ngang/chưa rõ thì mọi ô 'none'."""
    if not group_rule or not group_rule.get("rule"):
        return None
    if trend_dir not in (UP, DOWN):
        return dict.fromkeys(CELLS, "none")
    rule = group_rule["rule"]
    same = trend_dir == group_rule.get("when", "up")
    return {cell: rule[cell] if same else FLIP[rule[cell]] for cell in CELLS}
