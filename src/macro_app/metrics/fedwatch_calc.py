"""Xác suất FedWatch tự tính từ giá 30-Day Fed Funds futures (ZQ), theo phương pháp CME.

r_m = 100 - P_m. Tháng có họp ngày d (tháng N ngày): r_m = (d/N)*r_start + ((N-d)/N)*r_end.
r_start lấy r tháng trước nếu tháng đó không họp, không thì r_end kỳ trước (kỳ đầu: EFFR hiện hành).
Họp trong 7 ngày cuối tháng và tháng sau không họp thì r_end = r tháng sau.
Delta = r_end - r_start, k = floor(|Delta|/0.25), p = phần lẻ: bước k (1-p), bước k+1 (p).
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import pandas as pd

STEP_PCT = 0.25
STEP_BP = 25
LATE_MEETING_DAYS = 7
MONTH_CODES = "FGHJKMNQUVXZ"
SOURCE_COMPUTED = "Tự tính (ZQ)"
LONG_COLUMNS = ["asof", "meeting_date", "range_low_bp", "range_high_bp", "prob", "source"]
_EPS = 1e-9


def zq_ticker(period: pd.Period) -> str:
    """Ticker Yahoo của tháng hợp đồng, vd 2026-10 là 'ZQV26.CBT'."""
    return f"ZQ{MONTH_CODES[period.month - 1]}{period.year % 100:02d}.CBT"


def zq_period(ticker: str) -> pd.Period:
    """Tháng hợp đồng của ticker, vd 'ZQV26.CBT' là Period('2026-10', 'M')."""
    code, yy = ticker[2], int(ticker[3:5])
    return pd.Period(year=2000 + yy, month=MONTH_CODES.index(code) + 1, freq="M")


def zq_tickers_between(first: pd.Period, last: pd.Period) -> list[str]:
    return [zq_ticker(p) for p in pd.period_range(first, last, freq="M")]


def _month_rate(rates: dict[pd.Period, float], period: pd.Period) -> float | None:
    value = rates.get(period)
    return None if value is None or pd.isna(value) else float(value)


def _start_rate(period, rates, meeting_months, prev_end):
    prev = period - 1
    anchor = _month_rate(rates, prev) if prev not in meeting_months else None
    return anchor if anchor is not None else prev_end


def _end_rate(meeting: pd.Timestamp, rates, meeting_months, start: float) -> float | None:
    period = meeting.to_period("M")
    days, day = period.days_in_month, meeting.day
    nxt = period + 1
    next_anchor = _month_rate(rates, nxt) if nxt not in meeting_months else None
    if next_anchor is not None and days - day < LATE_MEETING_DAYS:
        return next_anchor
    avg = _month_rate(rates, period)
    if avg is not None and day < days:
        return (avg - day / days * start) / ((days - day) / days)
    return next_anchor


def meeting_rate_path(
    meetings: Iterable[pd.Timestamp], month_rates: dict[pd.Period, float], first_start: float
) -> pd.DataFrame:
    """r_start/r_end ngầm định cho từng kỳ họp (đã sắp xếp, đều sau ngày giá).

    Dừng ở kỳ họp đầu tiên không tính được (thiếu giá hợp đồng) vì chuỗi phía sau phụ thuộc nó.
    """
    meetings = sorted(pd.Timestamp(m) for m in meetings)
    meeting_months = {m.to_period("M") for m in meetings}
    rows, prev_end = [], first_start
    for meeting in meetings:
        start = _start_rate(meeting.to_period("M"), month_rates, meeting_months, prev_end)
        end = _end_rate(meeting, month_rates, meeting_months, start)
        if end is None:
            break
        rows.append({"meeting_date": meeting, "r_start": start, "r_end": end})
        prev_end = end
    return pd.DataFrame(rows, columns=["meeting_date", "r_start", "r_end"])


def move_distribution(delta_pct: float) -> dict[int, float]:
    """{số bước 25bp: xác suất} từ Delta (điểm %), vd Delta=-0.125 cho {0: 0.5, -1: 0.5}."""
    steps = abs(delta_pct) / STEP_PCT
    k = math.floor(steps + _EPS)
    frac = max(steps - k, 0.0)
    sign = -1 if delta_pct < 0 else 1
    dist = {sign * k: 1.0 - frac}
    if frac > _EPS:
        dist[sign * (k + 1)] = frac
    return dist


def _convolve(base: dict[int, float], move: dict[int, float]) -> dict[int, float]:
    out: dict[int, float] = {}
    for level, p_level in base.items():
        for step, p_step in move.items():
            out[level + step] = out.get(level + step, 0.0) + p_level * p_step
    return out


def chain_probabilities(
    path: pd.DataFrame, current_low_bp: int, asof: pd.Timestamp
) -> pd.DataFrame:
    """Tích chập xác suất các kỳ họp thành bảng dài theo khoảng mục tiêu 25bp."""
    rows, dist = [], {0: 1.0}
    deltas = (path["r_end"] - path["r_start"]).to_numpy()
    for meeting, delta in zip(path["meeting_date"], deltas, strict=True):
        dist = _convolve(dist, move_distribution(float(delta)))
        rows.extend(
            {
                "asof": asof,
                "meeting_date": meeting,
                "range_low_bp": current_low_bp + step * STEP_BP,
                "range_high_bp": current_low_bp + (step + 1) * STEP_BP,
                "prob": prob,
                "source": SOURCE_COMPUTED,
            }
            for step, prob in sorted(dist.items())
            if prob > _EPS
        )
    return pd.DataFrame(rows, columns=LONG_COLUMNS)


def compute_fedwatch(
    month_prices: dict[pd.Period, float],
    meetings: Iterable[pd.Timestamp],
    current_low_bp: int,
    first_start: float,
    asof: pd.Timestamp,
) -> pd.DataFrame:
    """Xác suất FedWatch cho 1 ngày giá. month_prices = {tháng hợp đồng: giá ZQ}."""
    asof = pd.Timestamp(asof).normalize()
    rates = {p: 100.0 - float(v) for p, v in month_prices.items() if pd.notna(v)}
    upcoming = [pd.Timestamp(m) for m in meetings if pd.Timestamp(m) > asof]
    path = meeting_rate_path(upcoming, rates, first_start)
    return chain_probabilities(path, int(current_low_bp), asof)


def asof_series(series: pd.DataFrame, series_id: str, asof: pd.Timestamp) -> float | None:
    """Giá trị gần nhất tới asof của 1 series trong store dài (series_id, date, value)."""
    sub = series[(series["series_id"] == series_id) & (series["date"] <= asof)]
    return None if sub.empty else float(sub.sort_values("date")["value"].iloc[-1])


def effr_spread(fred: pd.DataFrame, asof: pd.Timestamp, window: int = 5) -> float:
    """Trung vị (EFFR - điểm giữa biên) trên `window` quan sát gần nhất tới asof."""
    wide = (
        fred[fred["series_id"].isin(["fred.EFFR", "fred.DFEDTARU", "fred.DFEDTARL"])]
        .pivot_table(index="date", columns="series_id", values="value")
        .sort_index()
        .ffill()
    )
    wide = wide[wide.index <= asof].dropna()
    if wide.empty:
        return 0.0
    mid = (wide["fred.DFEDTARU"] + wide["fred.DFEDTARL"]) / 2
    return float((wide["fred.EFFR"] - mid).tail(window).median())


def current_target_low_bp(fred: pd.DataFrame, asof: pd.Timestamp | None = None) -> int | None:
    """Biên dưới khoảng mục tiêu (bp) tại asof từ store FRED (fred.DFEDTARL)."""
    asof = pd.Timestamp.max if asof is None else pd.Timestamp(asof)
    lower = asof_series(fred, "fred.DFEDTARL", asof)
    return None if lower is None else round(lower * 100)


def prices_wide(zq_prices: pd.DataFrame, ffill_limit: int = 3) -> pd.DataFrame:
    """Bảng rộng index=date, cột=Period tháng hợp đồng, từ zq_prices dài (date, ticker, close).

    Ngày có dưới 1/2 số hợp đồng có giá bị bỏ; ô thiếu lấp từ phiên trước (tối đa `ffill_limit`).
    """
    wide = zq_prices.pivot_table(index="date", columns="ticker", values="close").sort_index()
    wide.columns = [zq_period(t) for t in wide.columns]
    counts = wide.notna().sum(axis=1)
    wide = wide[counts >= counts.max() / 2]  # phiên đang chạy chỉ vài hợp đồng có giá
    return wide.ffill(limit=ffill_limit)


def compute_fedwatch_history(
    zq_prices: pd.DataFrame,
    meetings: Iterable[pd.Timestamp],
    fred: pd.DataFrame,
    n_days: int = 60,
) -> pd.DataFrame:
    """Xác suất tự tính cho `n_days` ngày giá gần nhất (mỗi ngày dùng biên/EFFR tại ngày đó)."""
    meetings = sorted(pd.Timestamp(m) for m in meetings)
    wide = prices_wide(zq_prices)
    parts = []
    for asof in wide.index[-n_days:]:
        low_bp = current_target_low_bp(fred, asof)
        upper = asof_series(fred, "fred.DFEDTARU", asof)
        if low_bp is None or upper is None:
            continue
        first_start = (low_bp / 100 + upper) / 2 + effr_spread(fred, asof)
        row = wide.loc[asof]
        result = compute_fedwatch(row.to_dict(), meetings, low_bp, first_start, asof)
        if not result.empty:
            parts.append(result)
    if not parts:
        return pd.DataFrame(columns=LONG_COLUMNS)
    return pd.concat(parts, ignore_index=True)


def range_label(low_bp: int, high_bp: int) -> str:
    return f"{int(low_bp)}–{int(high_bp)}"


def _latest(df: pd.DataFrame, asof: pd.Timestamp | None) -> pd.DataFrame:
    if df.empty:
        return df
    asof = pd.Timestamp(df["asof"].max() if asof is None else asof)
    return df[df["asof"] == asof]
