"""Trạng thái theo ngưỡng cấu hình (config/thresholds*.yaml).

cuts: k mốc tăng dần cho k + 1 mức (3 đến 5). side: above (tăng là xấu), below (tăng là tốt),
both (ở giữa là tốt), middle (ở giữa là xấu). Điểm so với mốc theo method: zscore = z trong N năm;
percentile = phân vị 0 đến 100 (both/middle: lệch so với P50); median_dev = lệch median N năm;
absolute = giá trị mới nhất; target_band = lệch mục tiêu Chính phủ.
Cấu hình dạng yellow/red (và absolute với khoảng green/yellow) vẫn được đọc.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import numpy as np
import pandas as pd

from macro_app.metrics.transforms import LAG_UNITS, MEASURE_KINDS, measure, zscore_latest

GREEN_STRONG, GREEN, YELLOW, ORANGE, RED = "green_strong", "green", "yellow", "orange", "red"
NO_THRESHOLD, INSUFFICIENT, NO_DATA = "none", "insufficient", "no_data"
STATUS_LABEL = {
    GREEN_STRONG: "Xanh đậm",
    GREEN: "Xanh",
    YELLOW: "Vàng",
    ORANGE: "Cam",
    RED: "Đỏ",
    NO_THRESHOLD: "Chưa đặt ngưỡng",
    INSUFFICIENT: "Chưa đủ dữ liệu",
    NO_DATA: "Chưa có dữ liệu",
}
LEVELS = {
    3: (GREEN, YELLOW, RED),
    4: (GREEN, YELLOW, ORANGE, RED),
    5: (GREEN_STRONG, GREEN, YELLOW, ORANGE, RED),
}
DEFAULT_LABELS = {
    3: ("Tốt", "Trung tính", "Xấu"),
    4: ("Tốt", "Trung tính", "Xấu", "Rất xấu"),
    5: ("Rất tốt", "Tốt", "Trung tính", "Xấu", "Rất xấu"),
}
METHODS = ("zscore", "percentile", "median_dev", "absolute", "target_band")
WINDOW_METHODS = ("zscore", "percentile", "median_dev")


@dataclass(frozen=True)
class StatusResult:
    status: str
    method: str
    threshold_source: str  # "default" | tên file ghi đè | ""
    score: float
    distance_to_next: float  # tới mốc xấu hơn kế tiếp, cùng đơn vị với score
    detail: str
    label: str = ""


def resolve_threshold(code: str, default: dict, overrides: dict) -> tuple[dict, str]:
    if code in overrides:
        override = overrides[code]
        inherited = {k: default[k] for k in ("window_years", "min_points", "side") if k in default}
        if override.get("method", default["method"]) == default["method"]:
            inherited = dict(default)  # cùng kiểu thì kế thừa cả mốc còn thiếu
        return {**inherited, **override}, override.get("_file", "override")
    return dict(default), "default"


def cuts_of(cfg: dict) -> list[float] | None:
    """Mốc của ngưỡng; cấu hình dạng yellow/red đọc thành [yellow, red]."""
    cuts = cfg.get("cuts")
    legacy = cfg.get("yellow") is not None and cfg.get("red") is not None
    if cuts is None and legacy and not isinstance(cfg["yellow"], list):
        cuts = [cfg["yellow"], cfg["red"]]
    return [float(c) for c in cuts] if cuts else None


def labels_of(cfg: dict, n_levels: int) -> list[str]:
    labels = cfg.get("labels")
    if labels and len(labels) == n_levels:
        return [str(x) for x in labels]
    return list(DEFAULT_LABELS.get(n_levels, ()))


def _measure_errors(cfg: dict) -> list[str]:
    spec = cfg.get("measure") or {}
    kind = spec.get("kind", "level")
    if kind not in MEASURE_KINDS:
        return [f"Cách đo không hợp lệ: {kind}"]
    lag_ok = (spec.get("n") or 0) >= 1 and spec.get("unit", "period") in LAG_UNITS
    if kind in ("change", "pct_change") and not lag_ok:
        return ["So với bao lâu trước: cần số ≥ 1 và đơn vị kỳ, ngày hoặc năm"]
    if kind == "mean" and not (
        (spec.get("n") or 0) >= 1 and spec.get("unit", "period") in ("period", "day")
    ):
        return ["Trung bình: cần số ≥ 1 và đơn vị kỳ hoặc ngày"]
    return []


def validate_cfg(cfg: dict) -> list[str]:
    """Lỗi cấu hình (dùng khi lưu từ giao diện)."""
    method, side = cfg.get("method"), cfg.get("side", "both")
    if method not in METHODS:
        return [f"Kiểu ngưỡng không hợp lệ: {method}"]
    errors = _measure_errors(cfg)
    cuts = cuts_of(cfg)
    if cfg.get("labels") and cuts and len(cfg["labels"]) != len(cuts) + 1:
        errors.append("Số tên mức phải bằng số mức")
    errors += _cut_errors(cfg, method, side, cuts)
    return errors


def _cut_errors(cfg: dict, method: str, side: str, cuts: list[float] | None) -> list[str]:
    errors = []
    if not cuts or not 2 <= len(cuts) <= 4:
        errors.append("Cần 2 đến 4 mốc (3 đến 5 mức)")
    elif any(b <= a for a, b in pairwise(cuts)):
        errors.append("Các mốc phải tăng dần")
    if method in WINDOW_METHODS and not (cfg.get("window_years") or 0) >= 1:
        errors.append("N năm phải từ 1 trở lên")
    if method == "percentile" and cuts:
        top = 50 if side in ("both", "middle") else 100
        if min(cuts) < 0 or max(cuts) > top:
            errors.append(f"Mốc phân vị phải trong khoảng 0–{top}")
    if method == "absolute" and side in ("both", "middle") and cuts and len(cuts) % 2:
        errors.append("Ngưỡng cứng hai phía cần số mốc chẵn (2 hoặc 4): nửa dưới và nửa trên")
    return errors


def _level_two_sided(score: float, cuts: list[float], side: str) -> tuple[int, float]:
    """Ngưỡng cứng hai phía: k mốc chẵn, vùng giữa hai mốc giữa là trung tâm.

    Mỗi mốc vượt ra ngoài thêm một bậc, bậc d ứng với mức 2d; 'middle' thì đảo lại.
    """
    cuts = sorted(cuts)
    half = len(cuts) // 2
    lower, upper = cuts[:half], cuts[half:]
    steps = sum(score < c for c in lower) + sum(score > c for c in upper)
    level = 2 * steps if side == "both" else len(cuts) - 2 * steps
    below = score < cuts[half]
    ahead = [c for c in (lower if below else upper) if (c < score if below else c > score)]
    if side == "both":  # mốc xa trung tâm hơn nằm ở phía giá trị đang đứng
        dist = min((abs(score - c) for c in ahead), default=0.0)
    else:
        dist = min(abs(score - c) for c in cuts)
    return level, dist


def _level(score: float, cuts: list[float], side: str, *, deviation: bool) -> tuple[int, float]:
    """Mức (0 = tốt nhất) và khoảng cách tới mốc xấu hơn kế tiếp.

    deviation=True: mốc là độ lệch dương; side below đảo dấu, both lấy trị tuyệt đối.
    deviation=False (ngưỡng cứng, phân vị một phía): mốc nằm trên thang giá trị.
    """
    if not deviation and side in ("both", "middle"):
        return _level_two_sided(score, cuts, side)
    if deviation and side == "middle":  # gần trung tâm là xấu: dưới mốc càng nhỏ càng xấu
        value = abs(score)
        worse = [c for c in cuts if value < c]
        nxt = max((c for c in cuts if c <= value), default=np.nan)
        return len(worse), (value - nxt) if not np.isnan(nxt) else 0.0
    if deviation:
        value = {"above": score, "below": -score}.get(side, abs(score))
    elif side == "below":
        worse = [c for c in cuts if score < c]
        nxt = max((c for c in cuts if c <= score), default=np.nan)
        return len(worse), (score - nxt) if not np.isnan(nxt) else 0.0
    else:
        value = score
    worse = [c for c in cuts if value > c]
    nxt = min((c for c in cuts if c >= value), default=np.nan)
    return len(worse), (nxt - value) if not np.isnan(nxt) else 0.0


def _window(s: pd.Series, years: int) -> pd.Series:
    return s[s.index > s.index[-1] - pd.DateOffset(years=years)]


def score_of(  # noqa: PLR0911
    s: pd.Series, cfg: dict, frequency: str, target: float
) -> tuple[float, str]:
    """Điểm đem so với mốc + diễn giải ngắn. NaN khi chưa đủ dữ liệu."""
    method, years = cfg["method"], int(cfg.get("window_years", 5))
    min_points = int((cfg.get("min_points") or {}).get(frequency, 8))
    latest = float(s.iloc[-1])
    if method == "zscore":
        z = zscore_latest(s, years, min_points)
        return z, f"z = {z:.2f}"
    if method in ("percentile", "median_dev"):
        w = _window(s, years)
        if len(w) < min_points:
            return np.nan, ""
        if method == "median_dev":
            dev = latest - float(w.median())
            return dev, f"lệch median {years} năm {dev:+.2f}"
        pct = float((w < latest).mean() * 100 + (w == latest).mean() * 50)
        score = pct - 50 if cfg.get("side", "both") in ("both", "middle") else pct
        return score, f"phân vị {pct:.0f} trong {years} năm"
    if method == "target_band":
        return (
            (latest - target, f"lệch mục tiêu {latest - target:+.2f}")
            if not np.isnan(target)
            else (np.nan, "")
        )
    return latest, ""


def _legacy_absolute(value: float, cfg: dict) -> str:
    def inside(ranges) -> bool:
        return any(
            (lo is None or value >= lo) and (hi is None or value <= hi) for lo, hi in ranges or []
        )

    if inside(cfg.get("green")):
        return GREEN
    return YELLOW if inside(cfg.get("yellow")) else RED


def evaluate(  # noqa: PLR0911
    series: pd.Series, frequency: str, cfg: dict, source: str, target_value: float = np.nan
) -> StatusResult:
    s = measure(series, frequency, cfg.get("measure"))
    method = cfg.get("method") or ""
    if s.empty:
        return StatusResult(NO_DATA, method, source, np.nan, np.nan, "")
    if method == "absolute" and cfg.get("cuts") is None and cfg.get("green") is not None:
        latest = float(s.iloc[-1])
        return StatusResult(_legacy_absolute(latest, cfg), method, source, latest, np.nan, "")
    cuts = cuts_of(cfg)
    if method not in METHODS or not cuts or len(cuts) + 1 not in LEVELS:
        return StatusResult(NO_THRESHOLD, method, source, np.nan, np.nan, "")
    two_sided = cfg.get("side", "both") in ("both", "middle")
    if method == "absolute" and two_sided and len(cuts) % 2:
        return StatusResult(NO_THRESHOLD, method, source, np.nan, np.nan, "")
    score, detail = score_of(s, cfg, frequency, target_value)
    if np.isnan(score):
        return StatusResult(INSUFFICIENT, method, source, np.nan, np.nan, detail)
    side = cfg.get("side", "both")
    deviation = method in ("zscore", "median_dev", "target_band") or (
        method == "percentile" and side in ("both", "middle")
    )
    level, dist = _level(score, cuts, side, deviation=deviation)
    label = labels_of(cfg, len(cuts) + 1)[level]
    return StatusResult(LEVELS[len(cuts) + 1][level], method, source, score, dist, detail, label)
