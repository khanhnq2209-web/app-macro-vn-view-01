"""Thao tác ghi của chế độ quản trị: lưu ngưỡng, refresh nguồn, gộp inbox.

Không import streamlit.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from macro_app.paths import CACHE_DIR, CONFIG_DIR

log = logging.getLogger(__name__)
UI_THRESHOLD_FILE = CONFIG_DIR / "thresholds.d" / "90_ui.yaml"
THRESHOLD_HISTORY_FILE = CONFIG_DIR / "thresholds_history.csv"


def _plain(v):  # noqa: PLR0911 — rẽ theo kiểu dữ liệu
    """np.float64/np.int64 → float; NaN/'' → None (yaml.safe_dump không ghi được kiểu numpy)."""
    if isinstance(v, list):
        return [_plain(x) for x in v]
    if isinstance(v, dict):
        out = {k: _plain(x) for k, x in v.items()}
        return {k: (int(x) if k == "n" and x is not None else x) for k, x in out.items()}
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, float, np.integer, np.floating)):
        return None if pd.isna(v) else float(v)
    return v


THRESHOLD_KEYS = ("method", "window_years", "cuts", "side", "description", "measure", "labels")


def _clean_cfg(cfg: dict) -> dict:
    out = {k: _plain(v) for k, v in cfg.items() if k in THRESHOLD_KEYS}
    if out.get("window_years") is not None:
        out["window_years"] = int(out["window_years"])
    return {k: v for k, v in out.items() if v is not None}


def validate_threshold(cfg: dict) -> None:
    from macro_app.metrics.status import validate_cfg

    errors = validate_cfg(_clean_cfg(cfg))
    if errors:
        raise ValueError("; ".join(errors))


def save_threshold(
    code: str, new_cfg: dict, old_cfg: dict, user: str, path: Path = UI_THRESHOLD_FILE
):
    """Ghi đè ngưỡng 1 chỉ số vào thresholds.d/90_ui.yaml + thêm dòng lịch sử."""
    validate_threshold(new_cfg)
    _write_ui_overrides(code, _clean_cfg(new_cfg), path)
    _append_history(code, old_cfg, _clean_cfg(new_cfg), user)


def reset_threshold(code: str, old_cfg: dict, user: str, path: Path = UI_THRESHOLD_FILE):
    """Bỏ ngưỡng riêng của chỉ số trong 90_ui.yaml → dùng lại ngưỡng mặc định (hoặc file khác)."""
    _write_ui_overrides(code, None, path)
    _append_history(code, old_cfg, {"method": "mặc định"}, user)


def _write_ui_overrides(code: str, cfg: dict | None, path: Path) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    data = data or {}
    if cfg is None:
        data.pop(code, None)
    else:
        data[code] = cfg
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "# Ghi bởi trang Ngưỡng (chế độ quản trị). Sửa tay được.\n"
    path.write_text(
        header + yaml.safe_dump(data, allow_unicode=True, sort_keys=True), encoding="utf-8"
    )


def _append_history(code: str, old_cfg: dict, new_cfg: dict, user: str) -> None:
    def dump(cfg: dict) -> str:
        return yaml.safe_dump(cfg, allow_unicode=True, default_flow_style=True).strip()

    row = {
        "at": datetime.now().replace(microsecond=0).isoformat(),
        "user": user,
        "code": code,
        "old": dump(_clean_cfg(old_cfg)),
        "new": dump(new_cfg),
    }
    hist = THRESHOLD_HISTORY_FILE
    old = pd.read_csv(hist) if hist.exists() else pd.DataFrame(columns=list(row))
    pd.concat([old, pd.DataFrame([row])], ignore_index=True).to_csv(
        hist, index=False, encoding="utf-8"
    )


SETS_DIR = CONFIG_DIR / "threshold_sets"


def _slug(name: str) -> str:
    import re
    import unicodedata

    ascii_name = unicodedata.normalize("NFKD", name.replace("đ", "d").replace("Đ", "D"))
    ascii_name = ascii_name.encode("ascii", "ignore").decode()
    return re.sub(r"[^0-9A-Za-z]+", "_", ascii_name).strip("_").lower()[:50] or "bo_nguong"


def save_threshold_set(
    name: str, description: str, items: dict, folder: Path | None = None
) -> Path:
    """Lưu bộ ngưỡng có tên. Mỗi mục được kiểm tra như khi lưu một ngưỡng."""
    folder = folder or SETS_DIR
    clean = {}
    for code, cfg in items.items():
        validate_threshold(cfg)
        clean[code] = _clean_cfg(cfg)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_slug(name)}.yaml"
    body = {"name": name.strip(), "description": description.strip(), "items": clean}
    path.write_text(yaml.safe_dump(body, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def set_active_threshold_sets(slugs: list[str], folder: Path | None = None) -> None:
    folder = folder or SETS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    header = "# Các bộ ngưỡng đang bật, bộ sau đè bộ trước (trống: chỉ dùng mặc định)\n"
    (folder / "_active.yaml").write_text(
        header + yaml.safe_dump({"active": list(slugs)}, allow_unicode=True), encoding="utf-8"
    )


def current_overrides() -> dict:
    """Ngưỡng riêng đang có hiệu lực (bộ đang chọn + sửa tay), để lưu thành bộ mới."""
    from macro_app.config import load_thresholds

    _, overrides = load_thresholds()
    return {code: {k: v for k, v in cfg.items() if k != "_file"} for code, cfg in overrides.items()}


def threshold_history(n: int = 10) -> pd.DataFrame:
    if not THRESHOLD_HISTORY_FILE.exists():
        return pd.DataFrame(columns=["at", "user", "code", "old", "new"])
    return pd.read_csv(THRESHOLD_HISTORY_FILE).tail(n).iloc[::-1]


def refresh_functions() -> dict[str, Callable[[], object]]:
    """Nguồn refresh được bằng nút.

    Import muộn: app công khai chỉ xem không cần thư viện mạng.
    """
    from macro_app.io import dulieukinhte_api, fedwatch, fred, simplize, vbma, westmetall, yahoo

    def run_simplize():
        panel = simplize.fetch_simplize_panel()
        return simplize.upsert_deposit_file(panel)

    return {
        "fred": lambda: fred.refresh_fred_cache(CACHE_DIR / "fred.xlsx"),
        "yahoo": lambda: yahoo.refresh_yahoo_cache(CACHE_DIR / "yahoo.xlsx"),
        "fedwatch": lambda: fedwatch.refresh_fedwatch_cache(CACHE_DIR / "fedwatch.xlsx"),
        "simplize": run_simplize,
        "vbma": lambda: vbma.fetch_vbma(CACHE_DIR / "vbma.xlsx"),
        "lme": lambda: westmetall.refresh_lme_cache(CACHE_DIR / "lme.xlsx"),
        "dulieukinhte": dulieukinhte_api.refresh_cache,
    }


SOURCE_LABEL = {
    "fred": "FRED",
    "yahoo": "Yahoo Finance",
    "fedwatch": "FedWatch (CME + tự tính)",
    "simplize": "Lãi suất huy động (Simplize)",
    "vbma": "VBMA",
    "lme": "Đồng LME (Westmetall)",
    "dulieukinhte": "Số liệu VN (dulieukinhte API)",
}


def _status_from_meta(result: object) -> str:
    """Fetcher ghi lỗi từng series vào _meta thay vì raise → đọc lại để báo đúng."""
    if isinstance(result, dict) and result.get("skipped"):  # dulieukinhte: tiết kiệm lượt gọi
        return f"bỏ qua: đã kéo lúc {result['fetched_at'][:10]}, chưa đủ ngày giãn cách"
    if isinstance(result, dict) and result.get("errors"):  # dulieukinhte: lỗi theo chuỗi
        return f"lỗi {len(result['errors'])} chuỗi — giữ dữ liệu cache cũ"
    if isinstance(result, pd.DataFrame) and "status" in result.columns and not result.empty:
        n_err = int((result["status"] != "ok").sum())
        if n_err:
            return f"lỗi {n_err}/{len(result)} series — giữ dữ liệu cache cũ"
    return "ok"


def refresh_sources(
    names: list[str], progress: Callable[[str, int, int], None] | None = None
) -> dict:
    """Chạy refresh từng nguồn; nguồn lỗi không chặn nguồn khác. Trả {nguồn: 'ok' | lỗi rút gọn}."""
    funcs = refresh_functions()
    results: dict[str, str] = {}
    for i, name in enumerate(names):
        if progress:
            progress(name, i, len(names))
        try:
            results[name] = _status_from_meta(funcs[name]())
        except Exception as exc:
            results[name] = f"{type(exc).__name__}: {str(exc)[:200]}"
            log.warning("Refresh %s lỗi: %s", name, results[name])
    return results


def merge_inbox() -> list[dict]:
    from macro_app.io import inbox_merge

    return inbox_merge.merge_inbox()


# ---------------- Bản đồ kế hoạch / dự báo ----------------
FORECAST_MAP_FILE = CONFIG_DIR / "forecast_map.yaml"
FORECAST_HEADER = (
    "# Bản đồ chỉ số thực tế → kế hoạch / dự báo (chỉ để tham khảo, không vào điểm scorecard).\n"
    "# Ghi bởi trang 'Kế hoạch & dự báo'. Loại: target | fedwatch | indicator | manual\n"
    "# (xem giải thích trong docs/spec.md, D14).\n"
)


def save_forecast_map(mappings: list[dict], path: Path | None = None) -> Path:
    """Ghi bản đồ (ghi nguyên tử: file tạm rồi thay)."""
    keys = ("code", "kind", "ref", "value", "period", "label", "note")
    rows = []
    for m in mappings:
        clean = {k: _plain(m.get(k)) for k in keys}
        if clean.get("period") is not None:
            clean["period"] = str(m["period"]).strip()
        rows.append({k: v for k, v in clean.items() if v not in (None, "")})
    file = path or FORECAST_MAP_FILE
    body = FORECAST_HEADER + yaml.safe_dump({"mappings": rows}, allow_unicode=True, sort_keys=False)
    tmp = file.with_name(file.name + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(file)
    return file
