"""Giá đồng LME (official cash-settlement, 3 tháng, tồn kho) từ bảng công khai của Westmetall.

Trang: https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash[&year=YYYY]
Mỗi năm 1 trang HTML; dòng: "05. October 2026 | 14,430.00 | 14,366.00 | 244,900".
Cache: data/cache/lme.xlsx (sheet/series + _meta). series_id: lme.copper_cash, lme.copper_3m,
lme.copper_stock. source = "LME (Westmetall)".
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from macro_app.io.excel_cache import merge_with_previous, read_cache, utc_now_iso, write_cache
from macro_app.paths import CACHE_DIR

log = logging.getLogger(__name__)
URL = "https://www.westmetall.com/en/markdaten.php"
SOURCE = "LME (Westmetall)"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
COLUMNS = {"lme.copper_cash": 1, "lme.copper_3m": 2, "lme.copper_stock": 3}
ROW = re.compile(
    r"<td[^>]*>\s*(\d{1,2}\. [A-Za-z]+ \d{4})\s*</td>\s*"
    r"<td[^>]*>\s*([\d,.\-]*)\s*</td>\s*<td[^>]*>\s*([\d,.\-]*)\s*</td>\s*<td[^>]*>\s*([\d,.\-]*)\s*</td>"
)
DEFAULT_CACHE = CACHE_DIR / "lme.xlsx"


def parse_table(html: str) -> pd.DataFrame:
    """HTML 1 năm → DataFrame[date, lme.copper_cash, lme.copper_3m, lme.copper_stock]."""
    rows = ROW.findall(html)
    if not rows:
        return pd.DataFrame(columns=["date", *COLUMNS])
    df = pd.DataFrame(rows, columns=["date", *COLUMNS])
    df["date"] = pd.to_datetime(df["date"], format="%d. %B %Y")
    for col in COLUMNS:
        df[col] = pd.to_numeric(df[col].str.replace(",", "", regex=False), errors="coerce")
    return df.drop_duplicates("date").sort_values("date")


def fetch_years(years: list[int | None], session: requests.Session, sleep: float) -> pd.DataFrame:
    parts = []
    for i, year in enumerate(years):
        params = {"action": "table", "field": "LME_Cu_cash"}
        if year is not None:
            params["year"] = year
        resp = session.get(URL, params=params, headers={"User-Agent": UA}, timeout=30)
        resp.raise_for_status()
        parts.append(parse_table(resp.text))
        if i < len(years) - 1:
            time.sleep(sleep)
    return pd.concat(parts, ignore_index=True).drop_duplicates("date").sort_values("date")


def refresh_lme_cache(
    cache_path: Path = DEFAULT_CACHE,
    start_year: int = 2010,
    sleep: float = 1.5,
    *,
    full: bool = False,
) -> pd.DataFrame:
    """Lần đầu (hoặc full) kéo từ start_year; các lần sau chỉ kéo năm hiện tại + năm trước."""
    old_frames, _ = read_cache(cache_path)
    this_year = date.today().year
    years: list[int | None] = [None, this_year - 1]  # None = trang năm hiện tại
    if full or not old_frames:
        years = [None, *range(start_year, this_year)]
    fetched_at = utc_now_iso()
    try:
        table = fetch_years(years, requests.Session(), sleep)
        error = ""
    except requests.RequestException as exc:
        table, error = pd.DataFrame(), f"{type(exc).__name__}: {str(exc)[:200]}"
        log.warning("Westmetall lỗi: %s", error)
    new_frames, meta_rows = {}, []
    for sid in COLUMNS:
        old = old_frames.get(sid, pd.DataFrame(columns=["date", "value"]))
        if not table.empty:
            fresh = table[["date", sid]].rename(columns={sid: "value"}).dropna()
            merged = (fresh if old.empty else pd.concat([old, fresh])).drop_duplicates(
                "date", keep="last"
            )
            merged = merged.sort_values("date")
            new_frames[sid] = merged.reset_index(drop=True)
        frame = new_frames.get(sid, old)
        meta_rows.append(
            {
                "series_id": sid,
                "sheet": sid,
                "fetched_at": fetched_at,
                "n_obs": len(frame),
                "last_date": frame["date"].max() if len(frame) else None,
                "status": "error" if error else "ok",
                "error": error,
            }
        )
    meta = pd.DataFrame(meta_rows)
    write_cache(cache_path, merge_with_previous(new_frames, old_frames), meta)
    return meta


def load_lme_series(cache_path: Path = DEFAULT_CACHE) -> pd.DataFrame:
    frames, _ = read_cache(cache_path)
    parts = [
        f[["date", "value"]].assign(series_id=sid, source=SOURCE)
        for sid, f in frames.items()
        if not f.empty
    ]
    if not parts:
        return pd.DataFrame(columns=["series_id", "date", "value", "source"])
    out = pd.concat(parts, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    return out[["series_id", "date", "value", "source"]]
