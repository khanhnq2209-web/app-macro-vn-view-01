"""Cache Excel dùng chung cho mọi fetcher: 1 file/nguồn, 1 sheet/series + sheet `_meta`.

`_meta` 1 dòng/series: series_id, sheet, fetched_at (ISO, UTC), n_obs, last_date, status, error.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

META_SHEET = "_meta"
_BAD_SHEET_CHARS = re.compile(r"[:\\/?*\[\]]")


def sheet_name_for(series_id: str) -> str:
    """Tên sheet hợp lệ cho Excel (≤31 ký tự, bỏ ký tự cấm)."""
    return _BAD_SHEET_CHARS.sub("_", series_id)[:31]


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def write_cache(path: Path, frames: dict[str, pd.DataFrame], meta: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.xlsx")
    with pd.ExcelWriter(tmp, engine="openpyxl") as writer:
        meta.to_excel(writer, sheet_name=META_SHEET, index=False)
        for name, df in frames.items():
            df.to_excel(writer, sheet_name=sheet_name_for(name), index=False)
    tmp.replace(path)  # ghi xong mới thay file cũ để lỗi giữa chừng không làm hỏng cache


def read_cache(path: Path) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    if not path.exists():
        return {}, pd.DataFrame()
    sheets = pd.read_excel(path, sheet_name=None)
    meta = sheets.pop(META_SHEET, pd.DataFrame())
    for df in sheets.values():
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
    return sheets, meta


def merge_with_previous(
    new_frames: dict[str, pd.DataFrame], old_frames: dict[str, pd.DataFrame]
) -> dict[str, pd.DataFrame]:
    """Series lỗi lần này (không có trong new_frames) giữ lại bản cache cũ."""
    merged = dict(old_frames)
    merged.update(new_frames)
    return merged


def cache_fetched_at(meta: pd.DataFrame) -> pd.Timestamp | None:
    """Thời điểm tải gần nhất thành công của cả file (max fetched_at có status ok)."""
    if meta.empty or "fetched_at" not in meta.columns:
        return None
    ok = meta[meta.get("status", "ok") == "ok"] if "status" in meta.columns else meta
    if ok.empty:
        return None
    return pd.to_datetime(ok["fetched_at"], utc=True).max()
