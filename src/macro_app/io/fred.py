"""FRED (St. Louis Fed) to Excel cache `data/cache/fred.xlsx` (1 sheet/series + `_meta`).

FRED dates monthly/quarterly/annual series at period start; stored as period end.
API key only from env `FRED_API_KEY`; never logged, stripped from every error message.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

import pandas as pd
import requests
import yaml
from dotenv import load_dotenv

from macro_app.io import excel_cache
from macro_app.paths import CACHE_DIR, CONFIG_DIR, ROOT

log = logging.getLogger(__name__)

API_BASE = "https://api.stlouisfed.org/fred"
SOURCE = "FRED"
PREFIX = "fred."
DEFAULT_CACHE = CACHE_DIR / "fred.xlsx"
REQUEST_SLEEP_SECONDS = 0.3  # FRED limit 120 req/min; 2 req/series
_PERIOD_END = {
    "M": pd.offsets.MonthEnd(0),
    "Q": pd.offsets.QuarterEnd(0),
    "A": pd.offsets.YearEnd(0),
}
_KEY_IN_URL = re.compile(r"api_key=[^&\s'\"]+")


def load_sources_config() -> dict:
    with open(CONFIG_DIR / "sources.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def get_api_key() -> str:
    load_dotenv(ROOT / ".env")
    return os.environ.get("FRED_API_KEY", "").strip()


def sanitize(message: str, api_key: str = "") -> str:
    """Bỏ key khỏi thông báo lỗi (requests nhét cả URL có api_key vào exception)."""
    text = _KEY_IN_URL.sub("api_key=***", str(message))
    if api_key:
        text = text.replace(api_key, "***")
    return text[:300]


def _get_json(session: requests.Session, endpoint: str, params: dict) -> dict:
    resp = session.get(f"{API_BASE}/{endpoint}", params=params, timeout=30)
    if resp.status_code != 200:
        try:
            detail = resp.json().get("error_message", "")
        except ValueError:
            detail = resp.text[:200]
        raise RuntimeError(f"HTTP {resp.status_code}: {detail}")
    return resp.json()


def observations_to_frame(observations: list[dict], frequency_short: str = "") -> pd.DataFrame:
    """JSON observations thành DataFrame[date, value]; FRED ghi '.' cho kỳ thiếu (bỏ dòng)."""
    raw = pd.DataFrame(observations, columns=["date", "value"])
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(raw["date"]).dt.normalize(),
            "value": pd.to_numeric(raw["value"], errors="coerce"),
        }
    ).dropna(subset=["value"])
    offset = _PERIOD_END.get(frequency_short[:1].upper()) if frequency_short else None
    if offset is not None:
        out["date"] = out["date"] + offset
    return out.reset_index(drop=True)


def _fetch_one(session: requests.Session, series_id: str, start: str, api_key: str) -> tuple:
    base = {"series_id": series_id, "api_key": api_key, "file_type": "json"}
    info = _get_json(session, "series", base)["seriess"][0]
    obs = _get_json(session, "series/observations", {**base, "observation_start": start})
    frame = observations_to_frame(obs.get("observations", []), info.get("frequency_short", ""))
    return frame, info


def _meta_row(series_id: str, frame: pd.DataFrame | None, info: dict, error: str = "") -> dict:
    ok = frame is not None and not frame.empty
    return {
        "series_id": PREFIX + series_id,
        "sheet": excel_cache.sheet_name_for(series_id),
        "fetched_at": excel_cache.utc_now_iso(),
        "n_obs": len(frame) if ok else 0,
        "last_date": frame["date"].max().date().isoformat() if ok else "",
        "status": "ok" if ok else "error",
        "error": error if not ok else "",
        "title": info.get("title", ""),
        "units": info.get("units", ""),
        "frequency": info.get("frequency", ""),
        "seasonal_adjustment": info.get("seasonal_adjustment_short", ""),
        "last_updated": info.get("last_updated", ""),
    }


def fetch_fred(
    ids: list[str], start: str, api_key: str, session: requests.Session | None = None
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Tải từng series; series lỗi ghi status=error trong meta, không dừng cả lượt."""
    session = session or requests.Session()
    frames: dict[str, pd.DataFrame] = {}
    rows = []
    for series_id in ids:
        frame, info, error = None, {}, ""
        try:
            if not api_key:
                raise RuntimeError("FRED_API_KEY chưa đặt")
            frame, info = _fetch_one(session, series_id, start, api_key)
            if frame.empty:
                error = "không có quan sát"
        except Exception as exc:  # 1 series lỗi không được dừng cả lượt
            error = sanitize(f"{type(exc).__name__}: {exc}", api_key)
            log.warning("FRED %s lỗi: %s", series_id, error)
        if frame is not None and not frame.empty:
            frames[series_id] = frame
        rows.append(_meta_row(series_id, frame, info, error))
        time.sleep(REQUEST_SLEEP_SECONDS)
    return frames, pd.DataFrame(rows)


def _keep_previous_meta(meta: pd.DataFrame, old_meta: pd.DataFrame) -> pd.DataFrame:
    """Series lỗi lần này: lấy lại title/units/n_obs/last_date của lần ok trước (sheet cũ giữ)."""
    if old_meta.empty:
        return meta
    old = old_meta.set_index("series_id")
    failed = meta["status"] != "ok"
    for col in ("n_obs", "last_date", "title", "units", "frequency"):
        if col in old.columns:
            meta.loc[failed, col] = (
                meta.loc[failed, "series_id"].map(old[col]).fillna(meta.loc[failed, col])
            )
    return meta


def refresh_fred_cache(
    cache_path: Path = DEFAULT_CACHE, ids: list[str] | None = None, start: str | None = None
) -> pd.DataFrame:
    config = load_sources_config()
    ids = ids or list(config["fred"])
    start = start or str(config.get("fetch_start", "2010-01-01"))
    frames, meta = fetch_fred(ids, start, get_api_key())
    old_frames, old_meta = excel_cache.read_cache(cache_path)
    named = {excel_cache.sheet_name_for(k): v for k, v in frames.items()}
    merged = excel_cache.merge_with_previous(named, old_frames)
    meta = _keep_previous_meta(meta, old_meta)
    known = set(meta["sheet"])
    extra = old_meta[~old_meta["sheet"].isin(known)] if not old_meta.empty else old_meta
    excel_cache.write_cache(cache_path, merged, pd.concat([meta, extra], ignore_index=True))
    return meta


def _sheet_to_series_id(meta: pd.DataFrame) -> dict[str, str]:
    if meta.empty or "sheet" not in meta.columns:
        return {}
    return dict(zip(meta["sheet"].astype(str), meta["series_id"].astype(str), strict=False))


def frames_to_long(
    frames: dict[str, pd.DataFrame], meta: pd.DataFrame, prefix: str, source: str
) -> pd.DataFrame:
    """Sheet cache thành store dài theo hợp đồng chung (series_id, date, value, source)."""
    mapping = _sheet_to_series_id(meta)
    parts = [
        pd.DataFrame(
            {
                "series_id": mapping.get(sheet, prefix + sheet),
                "date": pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize(),
                "value": pd.to_numeric(df["value"], errors="coerce").astype(float),
                "source": source,
            }
        )
        for sheet, df in frames.items()
        if {"date", "value"}.issubset(df.columns)
    ]
    if not parts:
        return pd.DataFrame(
            {
                "series_id": pd.Series(dtype=str),
                "date": pd.Series(dtype="datetime64[ns]"),
                "value": pd.Series(dtype=float),
                "source": pd.Series(dtype=str),
            }
        )
    out = pd.concat(parts, ignore_index=True).dropna(subset=["value"])
    out["date"] = out["date"].astype("datetime64[ns]")
    return out.sort_values(["series_id", "date"]).reset_index(drop=True)


def load_fred_series(cache_path: Path = DEFAULT_CACHE) -> pd.DataFrame:
    frames, meta = excel_cache.read_cache(cache_path)
    return frames_to_long(frames, meta, PREFIX, SOURCE)
