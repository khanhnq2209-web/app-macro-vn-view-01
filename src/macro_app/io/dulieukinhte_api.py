"""Kéo số liệu Việt Nam qua API chính thức của dulieukinhte.com (thay cho xuất Excel tay, D7).

- Key: biến môi trường `DLKT_API_KEY` (đăng ký miễn phí ở console.dulieukinhte.com/dang-ky).
  Gói miễn phí: 100 lượt/tháng, 10 lượt/phút, 5 năm lịch sử gần nhất.
- Gắn chuỗi của repo (`vn.*`) với mã chuỗi trên dulieukinhte: `config/dulieukinhte.yaml`.
  Tìm mã: `python -m macro_app.io.dulieukinhte_api find "tăng trưởng tín dụng"`.
- Kết quả lưu `data/cache/dulieukinhte.csv`; lúc build số API **đè** số trong file Excel cùng
  chuỗi, cùng kỳ (nguồn có sửa lùi số → bản mới thắng), và nối thêm kỳ mới.
Chỉ dùng API chính thức (`api.dulieukinhte.com/v1`); không gọi API nội bộ của web (robots.txt cấm).
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

from macro_app.config import read_yaml
from macro_app.paths import CACHE_DIR, CONFIG_DIR, ROOT

log = logging.getLogger(__name__)
BASE = "https://api.dulieukinhte.com/v1"
SOURCE = "dulieukinhte (API)"
CACHE_FILE = CACHE_DIR / "dulieukinhte.csv"
MAP_FILE = CONFIG_DIR / "dulieukinhte.yaml"
META_FILE = CACHE_DIR / "dulieukinhte_meta.json"  # lần kéo gần nhất (để không kéo dày)
DEFAULT_MIN_DAYS = 7  # gói miễn phí 100 lượt/tháng: mỗi chuỗi 1 lượt/lần kéo
PAUSE_SECONDS = 6.5  # gói miễn phí: 10 lượt/phút
STORE_COLUMNS = ["series_id", "date", "value", "source"]


def get_api_key() -> str:
    load_dotenv(ROOT / ".env")
    return os.environ.get("DLKT_API_KEY", "").strip()


def _session(key: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {key}", "Accept": "application/json"})
    return s


def _get(session: requests.Session, path: str, params: dict | None = None) -> dict:
    resp = session.get(f"{BASE}{path}", params=params or {}, timeout=30)
    if resp.status_code != 200:
        try:
            err = resp.json().get("error", {})
            message = f"{err.get('code', resp.status_code)}: {err.get('message', '')}"
        except ValueError:
            message = f"HTTP {resp.status_code}"
        raise RuntimeError(f"dulieukinhte {path}: {message}")  # không kèm header/key
    return resp.json()


def last_fetch(meta: Path = META_FILE) -> dict:
    import json

    return json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}


def min_days(path: Path = MAP_FILE) -> float:
    return float((read_yaml(path) if path.exists() else {}).get("min_days", DEFAULT_MIN_DAYS))


def load_map(path: Path = MAP_FILE) -> dict[str, dict]:
    """{series_id của repo: {id, note}}; dòng chưa có id thì bỏ qua lúc kéo."""
    return dict((read_yaml(path) if path.exists() else {}).get("series") or {})


def period_end(period: str) -> pd.Timestamp:
    """'2026-06' → 30/06/2026, '2026-Q2' → 30/06/2026, '2026' → 31/12/2026 (khớp lịch file raw)."""
    p = str(period)
    if "-Q" in p:
        year, q = p.split("-Q")
        return pd.Timestamp(year=int(year), month=int(q) * 3, day=1) + pd.offsets.MonthEnd(0)
    if len(p) == 4:
        return pd.Timestamp(year=int(p), month=12, day=31)
    if len(p) == 7:
        return pd.Timestamp(p + "-01") + pd.offsets.MonthEnd(0)
    return pd.Timestamp(p).normalize()


def fetch_series(session: requests.Session, sid: int, start: str) -> pd.DataFrame:
    """Toàn bộ quan sát của một chuỗi từ `start` (theo trang, cursor)."""
    rows, cursor = [], None
    while True:
        params = {"from": start, "order": "asc"}
        if cursor:
            params["cursor"] = cursor
        body = _get(session, f"/series/{sid}/observations", params)
        rows.extend(
            {"date": period_end(o.get("period") or o["date"]), "value": float(o["value"])}
            for o in body.get("data", {}).get("observations", [])
            if o.get("value") is not None
        )
        meta = body.get("meta", {})
        cursor = meta.get("nextCursor")
        if not meta.get("hasMore") or not cursor:
            break
        time.sleep(PAUSE_SECONDS)
    return pd.DataFrame(rows, columns=["date", "value"])


def refresh_cache(
    start: str | None = None,
    cache: Path = CACHE_FILE,
    *,
    force: bool = False,
    meta_file: Path = META_FILE,
    only: list[str] | None = None,
) -> dict:
    """Kéo mọi chuỗi đã gắn mã (1 lượt/chuỗi). Lần kéo trước chưa quá `min_days` ngày → bỏ qua,
    không tốn lượt (trừ khi force). Lỗi chuỗi nào ghi lại chuỗi đó. Trả meta cho nút Refresh.
    """
    prev = last_fetch(meta_file)
    if not force and not only and prev.get("fetched_at") and cache.exists():
        age = datetime.now(UTC) - datetime.fromisoformat(prev["fetched_at"])
        if age.total_seconds() < min_days() * 86400:
            return {**prev, "skipped": True, "errors": {}}
    key = get_api_key()
    if not key:
        raise RuntimeError(
            "Chưa có DLKT_API_KEY trong .env (đăng ký key miễn phí ở console.dulieukinhte.com)"
        )
    mapping = {k: v for k, v in load_map().items() if v and v.get("id")}
    if only:  # chỉ kéo vài chuỗi (vd chuỗi mới gắn), giữ nguyên các chuỗi khác trong cache
        mapping = {k: v for k, v in mapping.items() if k in only}
    if not mapping:
        raise RuntimeError("config/dulieukinhte.yaml chưa gắn mã chuỗi nào")
    start = start or f"{datetime.now(UTC).year - 5}-01-01"  # gói miễn phí: 5 năm gần nhất
    session = _session(key)
    parts, errors = [], {}
    for i, (series_id, spec) in enumerate(mapping.items()):
        if i:
            time.sleep(PAUSE_SECONDS)
        try:
            df = fetch_series(session, int(spec["id"]), start)
            parts.append(df.assign(series_id=series_id, source=SOURCE))
        except Exception as exc:  # ghi lỗi gọn, không in key
            errors[series_id] = str(exc)[:200]
            log.warning("dulieukinhte %s lỗi: %s", series_id, errors[series_id])
    new = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=STORE_COLUMNS)
    old = (
        pd.read_csv(cache, parse_dates=["date"])
        if cache.exists()
        else pd.DataFrame(columns=STORE_COLUMNS)
    )
    # chuỗi kéo được lần này thay hẳn bản cũ (nguồn có sửa lùi); chuỗi lỗi giữ bản cũ
    keep_old = old[~old["series_id"].isin(new["series_id"].unique())]
    frames = [f for f in (keep_old, new[STORE_COLUMNS]) if not f.empty]
    out = pd.concat(frames, ignore_index=True) if frames else new[STORE_COLUMNS]
    out = out.sort_values(["series_id", "date"]).reset_index(drop=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_name(cache.name + ".tmp")
    out.to_csv(tmp, index=False, encoding="utf-8")
    tmp.replace(cache)
    import json

    result = {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "series": len(mapping) - len(errors),
        "calls": len(mapping),
        "errors": errors,
    }
    if not only:  # kéo lẻ vài chuỗi không tính là một lần kéo đủ
        meta_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def load_series(cache: Path = CACHE_FILE) -> pd.DataFrame:
    """Store dài từ cache API (rỗng nếu chưa kéo lần nào)."""
    if not cache.exists():
        return pd.DataFrame(columns=STORE_COLUMNS)
    df = pd.read_csv(cache, parse_dates=["date"])
    return df[STORE_COLUMNS]


def overlay(store: pd.DataFrame, api: pd.DataFrame) -> pd.DataFrame:
    """Số API đè số cùng chuỗi, cùng kỳ trong store (bản mới thắng) và nối kỳ mới."""
    if api.empty:
        return store
    key = pd.MultiIndex.from_frame(api[["series_id", "date"]])
    hit = pd.MultiIndex.from_frame(store[["series_id", "date"]]).isin(key)
    return pd.concat([store[~hit], api], ignore_index=True)


def find(query: str) -> pd.DataFrame:
    """Tìm mã chuỗi theo tên (1 lượt API)."""
    session = _session(get_api_key())
    body = _get(session, "/search", {"q": query, "type": "series", "economy": "VN", "limit": 20})
    rows = body.get("data") or []
    return pd.DataFrame(
        [
            {
                "id": r.get("id"),
                "path": " › ".join(r.get("path") or [r.get("name", "")]),
                "frequency": r.get("frequency"),
                "unit": r.get("unit"),
                "lastUpdated": r.get("lastUpdated"),
            }
            for r in rows
        ]
    )


if __name__ == "__main__":  # python -m macro_app.io.dulieukinhte_api find "tăng trưởng tín dụng"
    if len(sys.argv) >= 3 and sys.argv[1] == "find":
        pd.set_option("display.width", 200)
        sys.stdout.write(find(" ".join(sys.argv[2:])).to_string(index=False) + "\n")
    else:
        sys.stdout.write(__doc__ or "")
