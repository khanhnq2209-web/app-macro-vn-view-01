"""Xem trước ngưỡng: quy mốc ra giá trị thật, chia dải màu, tính màu theo từng kỳ trong lịch sử."""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pandas as pd

from macro_app.metrics import transforms as tf
from macro_app.metrics.status import LEVELS, _level, cuts_of

DEVIATION = ("zscore", "median_dev", "target_band")


def is_deviation(method: str, side: str) -> bool:
    return method in DEVIATION or (method == "percentile" and side in ("both", "middle"))


def _window(s: pd.Series, years: int) -> pd.Series:
    return s[s.index > s.index[-1] - pd.DateOffset(years=years)]


def score_fn(s: pd.Series, cfg: dict, target: float):  # noqa: PLR0911
    """Hàm quy giá trị ra điểm theo phân phối cửa sổ N năm gần nhất (giống lúc chấm màu)."""
    method, side = cfg["method"], cfg.get("side", "both")
    w = _window(s, int(cfg.get("window_years", 5)))
    if method == "zscore":
        mean, std = w.mean(), w.std(ddof=1)
        return lambda v: (v - mean) / std if std else np.nan
    if method == "median_dev":
        med = w.median()
        return lambda v: v - med
    if method == "target_band":
        return lambda v: v - target
    if method == "percentile":
        arr = np.sort(w.to_numpy())
        center = 50.0 if side in ("both", "middle") else 0.0

        def pct(v):
            lo = np.searchsorted(arr, v, side="left")
            hi = np.searchsorted(arr, v, side="right")
            return (lo + hi) / 2 / len(arr) * 100 - center

        return pct
    return lambda v: v


def boundaries(s: pd.Series, cfg: dict, target: float) -> list[float]:
    """Mốc quy ra đơn vị của chỉ số (đường ranh giữa các màu trên biểu đồ)."""
    method, side, cuts = cfg["method"], cfg.get("side", "both"), cuts_of(cfg) or []
    w = _window(s, int(cfg.get("window_years", 5)))
    if method == "absolute":
        return sorted(cuts)
    if method == "percentile":
        qs = [50 - c for c in cuts] + [50 + c for c in cuts] if side in ("both", "middle") else cuts
        return sorted(float(np.percentile(w, q)) for q in qs if 0 <= q <= 100)
    if method == "zscore":
        center, scale = w.mean(), w.std(ddof=1)
    elif method == "median_dev":
        center, scale = w.median(), 1.0
    else:
        center, scale = target, 1.0
    if np.isnan(center):
        return []
    return sorted({center + sign * c * scale for c in cuts for sign in (1, -1)})


def status_of_score(score: float, cfg: dict) -> str:
    cuts = cuts_of(cfg)
    if not cuts or np.isnan(score) or len(cuts) + 1 not in LEVELS:
        return "none"
    method, side = cfg["method"], cfg.get("side", "both")
    level, _ = _level(score, cuts, side, deviation=is_deviation(method, side))
    return LEVELS[len(cuts) + 1][level]


def bands(
    s: pd.Series, cfg: dict, target: float, y_lo: float, y_hi: float
) -> list[tuple[float, float, str]]:
    """Các dải (từ, đến, màu) phủ khoảng [y_lo, y_hi] của biểu đồ."""
    fn = score_fn(s, cfg, target)
    edges = [y_lo] + [b for b in boundaries(s, cfg, target) if y_lo < b < y_hi] + [y_hi]
    out = []
    for lo, hi in pairwise(edges):
        out.append((lo, hi, status_of_score(fn((lo + hi) / 2), cfg)))
    return out


def history_scores(s: pd.Series, cfg: dict, frequency: str, target: pd.Series | None) -> pd.Series:  # noqa: PLR0911
    """Điểm tại từng kỳ, mỗi kỳ chỉ dùng dữ liệu tới kỳ đó (cửa sổ trượt N năm)."""
    method, side = cfg["method"], cfg.get("side", "both")
    years = int(cfg.get("window_years", 5))
    min_points = int((cfg.get("min_points") or {}).get(frequency, 8))
    win = f"{365 * years}D"
    s = tf.clean(s)
    if method == "absolute":
        return s
    if method == "zscore":
        return tf.rolling_zscore(s, years, min_points)
    if method == "median_dev":
        return s - s.rolling(win, min_periods=min_points).median()
    if method == "target_band":
        if target is None or target.empty:
            return pd.Series(np.nan, index=s.index)
        t = target.groupby(target.index.year).last()
        return s - pd.Series(s.index.year, index=s.index).map(t)

    def rank(x: np.ndarray) -> float:
        last = x[-1]
        return ((x < last).mean() + (x == last).mean() / 2) * 100

    pct = s.rolling(win, min_periods=min_points).apply(rank, raw=True)
    return pct - 50 if side in ("both", "middle") else pct


def level_shares(scores: pd.Series, cfg: dict) -> dict[str, float]:
    """Tỷ lệ số kỳ rơi vào từng màu (bỏ kỳ chưa đủ dữ liệu)."""
    statuses = scores.dropna().map(lambda x: status_of_score(x, cfg))
    if statuses.empty:
        return {}
    return (statuses.value_counts(normalize=True) * 100).round(0).to_dict()


def suggest_cuts(s: pd.Series, method: str, side: str, n_cuts: int, years: int) -> list[float]:  # noqa: PLR0911
    """Mốc gợi ý khi đổi kiểu hoặc số mức (người dùng sửa lại sau)."""
    w = _window(tf.clean(s), years) if not s.empty else s
    two_sided = side in ("both", "middle")
    if method == "zscore":
        return [round(x, 2) for x in np.linspace(1.0, 2.5, n_cuts)]
    if method == "percentile":
        top = 45 if two_sided else 95
        start = 15 if two_sided else 50
        return [round(x) for x in np.linspace(start, top, n_cuts)]
    if w.empty:
        return [float(i + 1) for i in range(n_cuts)]
    if method in ("median_dev", "target_band"):
        spread = float((w - w.median()).abs().quantile(0.9)) or 1.0
        return [round(x, 2) for x in np.linspace(spread / 3, spread, n_cuts)]
    qs = np.linspace(50, 90, n_cuts) if side == "above" else np.linspace(10, 50, n_cuts)
    return [round(float(np.percentile(w, q)), 2) for q in qs]
