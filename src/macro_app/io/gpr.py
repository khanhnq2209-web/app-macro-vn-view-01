"""Chỉ số rủi ro địa chính trị (GPR) của Caldara & Iacoviello, file tháng công khai.

Nguồn: https://www.matteoiacoviello.com/gpr.htm (trích dẫn: "Data downloaded from
https://www.matteoiacoviello.com/gpr.htm on <ngày tải>"). Chỉ số đếm tỷ lệ bài báo về rủi ro địa
chính trị; GPR = tổng, GPRT = mối đe dọa, GPRA = hành động. Tìm cột theo tên, không gắn vị trí.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import pandas as pd
import requests

from macro_app.io.excel_cache import merge_with_previous, read_cache, utc_now_iso, write_cache
from macro_app.paths import CACHE_DIR

log = logging.getLogger(__name__)
URL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls"
SOURCE = "GPR (Caldara & Iacoviello)"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
COLUMNS = {"gpr.gpr": "GPR", "gpr.threats": "GPRT", "gpr.acts": "GPRA"}
DEFAULT_CACHE = CACHE_DIR / "gpr.xlsx"


def parse_file(content: bytes) -> pd.DataFrame:
    """File .xls tháng thành DataFrame[date, gpr.gpr, gpr.threats, gpr.acts]."""
    raw = pd.read_excel(io.BytesIO(content), sheet_name=0)
    cols = {str(c).strip().upper(): c for c in raw.columns}
    date_col = cols.get("MONTH") or raw.columns[0]
    out = pd.DataFrame({"date": pd.to_datetime(raw[date_col], errors="coerce")})
    for sid, name in COLUMNS.items():
        if name in cols:
            out[sid] = pd.to_numeric(raw[cols[name]], errors="coerce")
    out = out.dropna(subset=["date"])
    out["date"] = out["date"] + pd.offsets.MonthEnd(0)  # kỳ tháng: ghi ngày cuối tháng
    return out.drop_duplicates("date").sort_values("date")


def refresh_gpr_cache(cache_path: Path = DEFAULT_CACHE, timeout: int = 180) -> pd.DataFrame:
    old_frames, _ = read_cache(cache_path)
    fetched_at = utc_now_iso()
    try:
        resp = requests.get(URL, headers={"User-Agent": UA}, timeout=timeout)
        resp.raise_for_status()
        table, error = parse_file(resp.content), ""
    except (requests.RequestException, ValueError) as exc:
        table, error = pd.DataFrame(), f"{type(exc).__name__}: {str(exc)[:200]}"
        log.warning("GPR lỗi: %s", error)
    new_frames, meta_rows = {}, []
    for sid in COLUMNS:
        old = old_frames.get(sid, pd.DataFrame(columns=["date", "value"]))
        if not table.empty and sid in table:
            new_frames[sid] = (
                table[["date", sid]].rename(columns={sid: "value"}).dropna().reset_index(drop=True)
            )
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


def load_gpr_series(cache_path: Path = DEFAULT_CACHE) -> pd.DataFrame:
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
