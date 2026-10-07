"""Simplize (đã có giấy phép, quyết định D6): LS huy động 20 NH → upsert `01_deposit rate.xlsx`.

API JSON công khai:
- `GET {base}/api/company/interest-rate/list?page=0&size=50` → danh sách NH
  (ticker, stockCode, name)
- `GET {base}/api/historical/interest-rate/{TICKER}` → lịch sử: maturity{N}m (%),
  date (epoch ms, 00:00 UTC)

File `01` giữ nguyên cột: ngay_du_lieu, ma_ngan_hang (= ticker), ten_ngan_hang, ma_ck, ky_han
("{N}_thang"), lai_suat_pct. Khóa upsert (ngay_du_lieu, ma_ngan_hang, ky_han), bản mới thắng.
"""

from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yaml

from macro_app.paths import BACKUP_DIR, CONFIG_DIR, DEPOSIT_FILE

log = logging.getLogger(__name__)

DEPOSIT_SHEET = "LS Lãi tiền gửi"
FILE_COLUMNS = ["ngay_du_lieu", "ma_ngan_hang", "ten_ngan_hang", "ma_ck", "ky_han", "lai_suat_pct"]
KEY_COLUMNS = ["ngay_du_lieu", "ma_ngan_hang", "ky_han"]
PANEL_COLUMNS = ["date", "bank_code", "bank_name", "stock_code", "tenor_m", "rate_pct"]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
TIMEOUT_SECONDS = 30


def simplize_config() -> dict:
    with open(CONFIG_DIR / "sources.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)["simplize"]


def _get_json(session: requests.Session, url: str) -> dict:
    resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)
    resp.raise_for_status()
    body = resp.json()
    if body.get("status") not in (200, None):
        raise ValueError(f"Simplize trả status {body.get('status')} cho {url}")
    return body


def fetch_bank_list(session: requests.Session, base_url: str) -> pd.DataFrame:
    """[bank_code, bank_name, stock_code] — bank_code = ticker Simplize."""
    body = _get_json(session, f"{base_url}/api/company/interest-rate/list?page=0&size=50")
    items = pd.DataFrame(body.get("data", []))
    return pd.DataFrame(
        {
            "bank_code": items["ticker"].astype(str),
            "bank_name": items.get("name", pd.Series(index=items.index, dtype=object)),
            "stock_code": items.get("stockCode", pd.Series(index=items.index, dtype=object)),
        }
    )


def history_to_panel(records: list[dict], tenors_m: list[int]) -> pd.DataFrame:
    """Bản ghi lịch sử 1 NH → [date, bank_code, tenor_m, rate_pct] (bỏ ô trống)."""
    frame = pd.DataFrame(records)
    if frame.empty or "date" not in frame.columns:
        return pd.DataFrame(columns=["date", "bank_code", "tenor_m", "rate_pct"])
    frame["date"] = (
        pd.to_datetime(frame["date"], unit="ms", utc=True).dt.tz_localize(None).dt.normalize()
    )
    columns = {f"maturity{n}m": n for n in tenors_m if f"maturity{n}m" in frame.columns}
    long = frame.melt(
        id_vars=["date", "ticker"],
        value_vars=list(columns),
        var_name="field",
        value_name="rate_pct",
    )
    long["tenor_m"] = long["field"].map(columns).astype(int)
    long["rate_pct"] = pd.to_numeric(long["rate_pct"], errors="coerce")
    long = long.dropna(subset=["rate_pct"]).rename(columns={"ticker": "bank_code"})
    return long[["date", "bank_code", "tenor_m", "rate_pct"]]


def fetch_simplize_panel(
    session: requests.Session | None = None, sleep: float = 1.5
) -> pd.DataFrame:
    """Toàn bộ lịch sử LS huy động mọi NH Simplize, kỳ hạn theo `sources.yaml`."""
    cfg = simplize_config()
    base, tenors = cfg["base_url"].rstrip("/"), [int(t) for t in cfg["tenors_m"]]
    session = session or requests.Session()
    banks = fetch_bank_list(session, base)
    parts = []
    for code in banks["bank_code"]:
        time.sleep(sleep)
        body = _get_json(session, f"{base}/api/historical/interest-rate/{code}")
        parts.append(history_to_panel(body.get("data", []), tenors))
        log.info("Simplize %s: %d dòng", code, len(parts[-1]))
    panel = pd.concat(parts, ignore_index=True).merge(banks, on="bank_code", how="left")
    panel = panel.drop_duplicates(["date", "bank_code", "tenor_m"], keep="last")
    return panel[PANEL_COLUMNS].sort_values(["date", "bank_code", "tenor_m"], ignore_index=True)


def panel_to_file_rows(panel: pd.DataFrame) -> pd.DataFrame:
    """Panel → đúng cột của sheet `LS Lãi tiền gửi`."""
    return pd.DataFrame(
        {
            "ngay_du_lieu": pd.to_datetime(panel["date"]).dt.normalize(),
            "ma_ngan_hang": panel["bank_code"].astype(str),
            "ten_ngan_hang": panel["bank_name"],
            "ma_ck": panel["stock_code"],
            "ky_han": panel["tenor_m"].astype(int).astype(str) + "_thang",
            "lai_suat_pct": pd.to_numeric(panel["rate_pct"], errors="coerce").astype(float),
        }
    )


def backup_file(path: Path, backup_dir: Path, stamp: str | None = None) -> Path:
    """Chép `path` vào `backup_dir/<timestamp>/` trước khi ghi."""
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / stamp / path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return target


def upsert_rows(old: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Gộp theo khóa, bản mới thắng. Trả (bảng gộp, {rows_added, rows_changed})."""
    old = old.assign(ngay_du_lieu=pd.to_datetime(old["ngay_du_lieu"]).dt.normalize())
    new = new.drop_duplicates(KEY_COLUMNS, keep="last")
    joined = new.merge(
        old[[*KEY_COLUMNS, "lai_suat_pct"]],
        on=KEY_COLUMNS,
        how="left",
        suffixes=("", "_old"),
        indicator=True,
    )
    is_new = joined["_merge"].eq("left_only")
    old_rate = pd.to_numeric(joined["lai_suat_pct_old"], errors="coerce").to_numpy(dtype=float)
    new_rate = joined["lai_suat_pct"].to_numpy(dtype=float)
    changed = ~is_new & ~np.isclose(old_rate, new_rate, rtol=0, atol=1e-9, equal_nan=True)
    kept = old.merge(new[KEY_COLUMNS], on=KEY_COLUMNS, how="left", indicator=True)
    kept = kept[kept["_merge"].eq("left_only")].drop(columns="_merge")
    merged = pd.concat([kept, new], ignore_index=True)[FILE_COLUMNS]
    merged = merged.sort_values(KEY_COLUMNS, ignore_index=True)
    return merged, {"rows_added": int(is_new.sum()), "rows_changed": int(changed.sum())}


def upsert_deposit_file(
    new_panel: pd.DataFrame, path: Path = DEPOSIT_FILE, backup_dir: Path = BACKUP_DIR
) -> dict:
    """Sao lưu rồi upsert panel mới vào sheet `LS Lãi tiền gửi` của file `01`."""
    old = pd.read_excel(path, sheet_name=DEPOSIT_SHEET, engine="openpyxl")
    stats = {
        "rows_before": len(old),
        "max_date_before": pd.to_datetime(old["ngay_du_lieu"]).max(),
    }
    new_rows = panel_to_file_rows(new_panel).dropna(subset=["lai_suat_pct"])
    merged, counts = upsert_rows(old, new_rows)
    stats |= counts | {"rows_after": len(merged), "max_date_after": merged["ngay_du_lieu"].max()}
    if counts["rows_added"] == 0 and counts["rows_changed"] == 0:
        return stats | {"written": False, "backup": None}
    backup = backup_file(path, backup_dir)
    with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        merged.to_excel(writer, sheet_name=DEPOSIT_SHEET, index=False)
    return stats | {"written": True, "backup": str(backup)}
