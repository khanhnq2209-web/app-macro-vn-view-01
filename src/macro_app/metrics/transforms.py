"""Biến đổi chuỗi thời gian thuần (pd.Series có DatetimeIndex), không I/O.

Quy ước kỳ: tháng = cuối tháng, quý = cuối quý, năm = 31/12.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PERIOD_RULE = {"M": "ME", "Q": "QE", "A": "YE"}
PERIODS_PER_YEAR = {"M": 12, "Q": 4, "A": 1}


def clean(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").dropna()
    s.index = pd.DatetimeIndex(s.index).normalize()
    return s[~s.index.duplicated(keep="last")].sort_index()


def to_period(series: pd.Series, freq: str, how: str = "last") -> pd.Series:
    """Đưa về lưới kỳ đều (M/Q/A), kỳ thiếu để NaN; D/W giữ nguyên."""
    s = clean(series)
    if freq not in PERIOD_RULE or s.empty:
        return s
    resampled = s.resample(PERIOD_RULE[freq])
    return resampled.mean() if how == "mean" else resampled.last()


def quarter_end_values(monthly: pd.Series) -> pd.Series:
    """Chuỗi tháng lặp lại số quý (vd heatmap VBMA): chỉ giữ tháng cuối quý.

    Quý chưa có tháng cuối (vd T7, T8 lặp số Q2) bị bỏ để không tạo quý chưa công bố.
    """
    s = clean(monthly)
    s = s[s.index.month.isin([3, 6, 9, 12])]
    s.index = s.index + pd.offsets.QuarterEnd(0)
    return s


def value_year_ago(series: pd.Series) -> pd.Series:
    """Giá trị gần nhất trước hoặc đúng 1 năm trước mỗi ngày (cho chuỗi D/W)."""
    s = clean(series)
    lagged = s.index - pd.DateOffset(
        years=1
    )  # 29/02 và 28/02 cùng rơi vào 28/02 nên tra theo vị trí
    pos = s.index.searchsorted(lagged, side="right") - 1
    values = np.where(pos >= 0, s.to_numpy()[np.clip(pos, 0, None)], np.nan)
    return pd.Series(values, index=s.index)


def yoy_pct(series: pd.Series, freq: str) -> pd.Series:
    """% thay đổi so cùng kỳ năm trước của chuỗi mức."""
    if freq in PERIODS_PER_YEAR:
        s = to_period(series, freq)
        return (s / s.shift(PERIODS_PER_YEAR[freq]) - 1.0) * 100.0
    s = clean(series)
    return (s / value_year_ago(s) - 1.0) * 100.0


def mom_to_index(mom_pct: pd.Series) -> pd.Series:
    """Chỉ số tích lũy từ % MoM trên lưới tháng đều; tháng thiếu làm đứt chuỗi (NaN lan về sau)."""
    m = to_period(mom_pct, "M")
    return (1.0 + m / 100.0).cumprod(skipna=False) * 100.0


def mom_to_yoy(mom_pct: pd.Series) -> pd.Series:
    idx = mom_to_index(mom_pct)
    return (idx / idx.shift(12) - 1.0) * 100.0


def mom_to_avg_ytd(mom_pct: pd.Series) -> pd.Series:
    """CPI bình quân từ đầu năm: TB chỉ số T1..t năm nay / TB T1..t năm trước - 1."""
    idx = mom_to_index(mom_pct)
    avg_ytd = idx.groupby(idx.index.year).expanding().mean().droplevel(0)
    prev = avg_ytd.shift(12)
    return (avg_ytd / prev - 1.0) * 100.0


def ytd_to_yoy(ytd_pct: pd.Series) -> pd.Series:
    """% so cùng kỳ từ chuỗi % tăng trưởng từ đầu năm (vd tín dụng), không cần số dư.

    yoy(t) = (1 + ytd(t)) * (1 + ytd(tháng 12 năm trước)) / (1 + ytd(cùng tháng năm trước)) - 1
    """
    m = to_period(ytd_pct, "M") / 100.0
    dec = m[m.index.month == 12]
    prev_dec = pd.Series(m.index.year - 1, index=m.index).map(
        pd.Series(dec.to_numpy(), index=dec.index.year)
    )
    return ((1 + m) * (1 + prev_dec) / (1 + m.shift(12)) - 1) * 100.0


MEASURE_KINDS = (
    "level",
    "change",
    "pct_change",
    "ytd_change",
    "ytd_pct",
    "mean",
    "sum12_pct",
    "pct_vs_mean",
)
LAG_UNITS = ("period", "day", "year")


def lagged(series: pd.Series, freq: str, n: int, unit: str) -> pd.Series:
    """Giá trị n kỳ / ngày / năm trước của mỗi điểm (theo lịch, không theo số điểm)."""
    s = clean(series)
    if unit == "period" and freq in PERIOD_RULE:
        grid = to_period(s, freq)
        return grid.shift(n).reindex(s.index)
    if unit == "period":
        return s.shift(n)
    offset = pd.DateOffset(years=n) if unit == "year" else pd.DateOffset(days=n)
    pos = s.index.searchsorted(s.index - offset, side="right") - 1
    values = np.where(pos >= 0, s.to_numpy()[np.clip(pos, 0, None)], np.nan)
    return pd.Series(values, index=s.index)


def measure(series: pd.Series, freq: str, spec: dict | None) -> pd.Series:  # noqa: PLR0911
    """Chuỗi đem so với ngưỡng: giá trị gốc hoặc biến đổi (thay đổi, % thay đổi, từ đầu năm)."""
    s = clean(series)
    spec = spec or {}
    kind = spec.get("kind", "level")
    if kind == "level" or s.empty:
        return s
    if kind == "mean":
        return rolling_mean(s, int(spec.get("n", 1)), spec.get("unit", "period"))
    if kind == "sum12_pct":
        return sum12_pct(s, from_ytd=bool(spec.get("ytd")))
    if kind == "pct_vs_mean":
        return pct_vs_mean(s, int(spec.get("n", 5)))
    if kind in ("ytd_change", "ytd_pct"):
        year_end = s.groupby(s.index.year).last()
        base = pd.Series(s.index.year - 1, index=s.index).map(year_end)
    else:
        base = lagged(s, freq, int(spec.get("n", 1)), spec.get("unit", "period"))
    if kind in ("pct_change", "ytd_pct"):
        return ((s / base - 1.0) * 100.0).dropna()
    return (s - base).dropna()


def pct_vs_mean(s: pd.Series, years: int) -> pd.Series:
    """% lệch của giá trị so với trung bình `years` năm trước đó (tính cả điểm hiện tại).

    Dùng cho giá (dầu, khí): đo mức đắt / rẻ so với nền nhiều năm, không bị hiệu ứng nền
    như % so cùng kỳ. Chỉ tính khi đã có đủ `years` năm số liệu.
    """
    s = clean(s)
    if s.empty:
        return s
    mean = s.rolling(f"{365 * years}D").mean()
    ready = s.index >= s.index[0] + pd.DateOffset(years=years)
    return ((s / mean - 1.0) * 100.0)[ready].dropna()


def rolling_mean(s: pd.Series, n: int, unit: str) -> pd.Series:
    """Trung bình trượt n kỳ (số điểm) hoặc n ngày lịch; đủ cửa sổ mới tính."""
    s = clean(s)
    if unit == "day":
        mean = s.rolling(f"{n}D").mean()
        start = s.index[0] + pd.DateOffset(days=n - 1)
        return mean[mean.index >= start]
    return s.rolling(n, min_periods=n).mean().dropna()


def sum12_pct(series: pd.Series, *, from_ytd: bool = False) -> pd.Series:
    """Tổng 12 tháng trượt của chuỗi dòng tháng, % so cùng kỳ năm trước.

    from_ytd=True: chuỗi gốc là lũy kế từ đầu năm, tách ra số từng tháng trước khi cộng.
    Thiếu tháng nào trong cửa sổ thì không tính (không nội suy).
    """
    m = to_period(clean(series), "M")
    if from_ytd:
        prev = m.groupby(m.index.year).shift(1)
        prev = prev.where(m.index.month != 1, 0.0)  # tháng 1: số lũy kế chính là số tháng
        m = m - prev  # tháng thiếu hoặc chuỗi bắt đầu giữa năm ra NaN, cửa sổ chứa nó bị loại
    total = m.rolling(12, min_periods=12).sum()
    return ((total / total.shift(12) - 1.0) * 100.0).dropna()


def ytd_change_pct(series: pd.Series) -> pd.Series:
    """% thay đổi so với giá trị cuối năm trước (vd tỷ giá)."""
    s = clean(series)
    year_end = s.groupby(s.index.year).last()
    base = pd.Series(s.index.year - 1, index=s.index).map(year_end)
    return (s / base - 1.0) * 100.0


def ytd_sum(monthly_flow: pd.Series) -> pd.Series:
    """Lũy kế từ đầu năm của chuỗi dòng tháng; thiếu một tháng thì các tháng sau trong năm trống."""
    m = to_period(monthly_flow, "M")
    return m.groupby(m.index.year).cumsum(skipna=False).dropna()


def plan_pace(monthly_flow: pd.Series, plans: dict[int, float]) -> pd.Series:
    """Tiến độ so kế hoạch năm (điểm %): % kế hoạch đã đạt - % thời gian đã trôi (tháng/12).

    Chỉ tính cho năm có kế hoạch. Vd 9 tháng đạt 64,2% kế hoạch: 64,2 - 75 = -10,8.
    """
    cum = ytd_sum(monthly_flow)
    plan = pd.Series(cum.index.year, index=cum.index).map(plans)
    pct = cum / plan * 100.0
    elapsed = pd.Series(cum.index.month / 12 * 100.0, index=cum.index)
    return (pct - elapsed).dropna()


def ytd_sum_yoy(monthly_flow: pd.Series) -> pd.Series:
    """Lũy kế từ đầu năm của chuỗi dòng tháng, % so cùng kỳ năm trước."""
    m = to_period(monthly_flow, "M")
    cum = m.groupby(m.index.year).cumsum(skipna=False)
    return (cum / cum.shift(12) - 1.0) * 100.0


def extend(primary: pd.Series, secondary: pd.Series) -> pd.Series:
    """Nối chuỗi phụ sau ngày cuối của chuỗi chính (vd Brent FRED + Yahoo số mới)."""
    p, s = clean(primary), clean(secondary)
    if p.empty:
        return s
    return pd.concat([p, s[s.index > p.index.max()]])


def align_diff(a: pd.Series, b: pd.Series, freq: str) -> pd.Series:
    """a - b trên lưới kỳ `freq` (giá trị cuối kỳ), chỉ kỳ có đủ cả hai."""
    left, right = to_period(a, freq), to_period(b, freq)
    return (left - right).dropna()


def change(value: float, previous: float, change_unit: str) -> float:
    """Thay đổi theo kiểu catalog: bps/pp là hiệu số, pct là % tương đối."""
    if previous is None or value is None or np.isnan(previous) or np.isnan(value):
        return np.nan
    if change_unit == "pct":
        return np.nan if previous == 0 else (value / previous - 1.0) * 100.0
    diff = value - previous
    return diff * 100.0 if change_unit == "bps" else diff


def previous_value(series: pd.Series, freq: str, daily_window_days: int) -> tuple:
    """(ngày, giá trị) của kỳ so sánh: kỳ liền trước; chuỗi ngày lấy giá trị cách N ngày."""
    s = clean(series)
    if len(s) < 2:
        return None, np.nan
    if freq == "D":
        cutoff = s.index[-1] - pd.Timedelta(days=daily_window_days)
        before = s[s.index <= cutoff]
        return (before.index[-1], before.iloc[-1]) if not before.empty else (None, np.nan)
    return s.index[-2], s.iloc[-2]


def same_period_last_year(series: pd.Series, freq: str) -> float:
    s = clean(series)
    if s.empty:
        return np.nan
    if freq in PERIODS_PER_YEAR:
        target = s.index[-1] - pd.DateOffset(years=1)
        target = target + pd.offsets.MonthEnd(0) if freq != "A" else target
        hit = s[s.index == target.normalize()]
        return hit.iloc[0] if not hit.empty else np.nan
    return value_year_ago(s).iloc[-1]


def last_value_prev_year(series: pd.Series) -> float:
    s = clean(series)
    if s.empty:
        return np.nan
    prev = s[s.index.year < s.index[-1].year]
    return prev.iloc[-1] if not prev.empty else np.nan


def zscore_latest(series: pd.Series, window_years: int, min_points: int) -> float:
    """z của điểm mới nhất so với cửa sổ N năm kết thúc tại điểm đó."""
    s = clean(series)
    if s.empty:
        return np.nan
    window = s[s.index > s.index[-1] - pd.DateOffset(years=window_years)]
    if len(window) < min_points:
        return np.nan
    std = window.std(ddof=1)
    return np.nan if not std or np.isnan(std) else (window.iloc[-1] - window.mean()) / std


def rolling_zscore(series: pd.Series, window_years: int, min_points: int) -> pd.Series:
    s = clean(series)
    window = f"{365 * window_years}D"
    mean = s.rolling(window, min_periods=min_points).mean()
    std = s.rolling(window, min_periods=min_points).std()
    return (s - mean) / std.replace(0, np.nan)
