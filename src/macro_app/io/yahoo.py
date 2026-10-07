"""Yahoo Finance (yfinance) vào cache `data/cache/yahoo.xlsx` (1 sheet/ticker + `_meta`).

value = Close (auto_adjust=False). Nghỉ `YF_SLEEP_SECONDS` giữa các ticker để tránh HTTP 429.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

from macro_app.io import excel_cache
from macro_app.io.fred import frames_to_long, load_sources_config
from macro_app.paths import CACHE_DIR, ROOT

log = logging.getLogger(__name__)

SOURCE = "Yahoo"
PREFIX = "yahoo."
DEFAULT_CACHE = CACHE_DIR / "yahoo.xlsx"
_COLUMNS = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}


def sleep_seconds() -> float:
    load_dotenv(ROOT / ".env")
    try:
        return float(os.environ.get("YF_SLEEP_SECONDS", "1.0"))
    except ValueError:
        return 1.0


def history_to_frame(history: pd.DataFrame) -> pd.DataFrame:
    """yfinance history (index ngày, có thể có tz) thành DataFrame chuẩn của cache."""
    if history is None or history.empty or "Close" not in history.columns:
        return pd.DataFrame(columns=["date", *_COLUMNS.values(), "value"])
    out = history.rename(columns=_COLUMNS).reindex(columns=list(_COLUMNS.values()))
    index = pd.DatetimeIndex(history.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    out.insert(0, "date", index.normalize())
    out["value"] = out["close"].astype(float)
    out = out.dropna(subset=["value"]).drop_duplicates("date", keep="last")
    return out.sort_values("date").reset_index(drop=True)


def _download(ticker: str, start: str) -> pd.DataFrame:
    return yf.Ticker(ticker).history(start=start, auto_adjust=False, actions=False)


def _meta_row(ticker: str, frame: pd.DataFrame | None, error: str = "") -> dict:
    ok = frame is not None and not frame.empty
    return {
        "series_id": PREFIX + ticker,
        "sheet": excel_cache.sheet_name_for(ticker),
        "fetched_at": excel_cache.utc_now_iso(),
        "n_obs": len(frame) if ok else 0,
        "last_date": frame["date"].max().date().isoformat() if ok else "",
        "status": "ok" if ok else "error",
        "error": "" if ok else error,
    }


def fetch_yahoo(
    tickers: list[str], start: str, pause: float | None = None
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Tải từng ticker; ticker lỗi hoặc không có dữ liệu ghi status=error, không dừng cả lượt."""
    pause = sleep_seconds() if pause is None else pause
    frames: dict[str, pd.DataFrame] = {}
    rows = []
    for i, ticker in enumerate(tickers):
        if i and pause > 0:
            time.sleep(pause)
        frame, error = None, ""
        try:
            frame = history_to_frame(_download(ticker, start))
            if frame.empty:
                error = "không có dữ liệu (ticker sai/hết hạn hoặc bị chặn)"
        except Exception as exc:  # 1 ticker lỗi không được dừng cả lượt
            error = f"{type(exc).__name__}: {exc}"[:300]
            log.warning("Yahoo %s lỗi: %s", ticker, error)
        if frame is not None and not frame.empty:
            frames[ticker] = frame
        rows.append(_meta_row(ticker, frame, error))
    return frames, pd.DataFrame(rows)


def refresh_yahoo_cache(
    cache_path: Path = DEFAULT_CACHE, tickers: list[str] | None = None, start: str | None = None
) -> pd.DataFrame:
    config = load_sources_config()
    tickers = tickers or list(config["yahoo"])
    start = start or str(config.get("fetch_start", "2010-01-01"))
    frames, meta = fetch_yahoo(tickers, start)
    old_frames, old_meta = excel_cache.read_cache(cache_path)
    named = {excel_cache.sheet_name_for(k): v for k, v in frames.items()}
    merged = excel_cache.merge_with_previous(named, old_frames)
    extra = old_meta[~old_meta["sheet"].isin(set(meta["sheet"]))] if not old_meta.empty else None
    excel_cache.write_cache(cache_path, merged, pd.concat([meta, extra], ignore_index=True))
    return meta


def load_yahoo_series(cache_path: Path = DEFAULT_CACHE) -> pd.DataFrame:
    frames, meta = excel_cache.read_cache(cache_path)
    return frames_to_long(frames, meta, PREFIX, SOURCE)
