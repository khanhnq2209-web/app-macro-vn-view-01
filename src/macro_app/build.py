"""Bước build: raw + cache thành data/app (store nội bộ cho app) và data/public (file công khai).

data/public không chứa số của nguồn có giấy phép (Yahoo, LME).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from macro_app import config as cfgmod
from macro_app.io import manual as manual_io
from macro_app.metrics.recipes import RawContext, compute_all, rebase_input
from macro_app.metrics.summary import summarize
from macro_app.paths import APP_DIR, CACHE_DIR, PUBLIC_DIR

log = logging.getLogger(__name__)
STORE_COLUMNS = ["series_id", "date", "value", "source"]
VENDOR_SOURCES = ("Yahoo", "LME (Westmetall)")  # không ghi ra data/public
HISTORY_FILE = "status_history.csv"
RAW_STORE_FILE = "_raw_store.parquet"  # bản sao store raw cho rescore (không commit)


def _safe_load(name: str, loader: Callable[[], pd.DataFrame], errors: dict) -> pd.DataFrame:
    """Một nguồn lỗi không làm hỏng cả build: ghi lỗi (đã rút gọn) vào build_meta."""
    try:
        df = loader()
    except Exception as exc:
        errors[name] = f"{type(exc).__name__}: {str(exc)[:200]}"
        log.warning("Nguồn %s lỗi: %s", name, errors[name])
        return pd.DataFrame(columns=STORE_COLUMNS)
    return df[STORE_COLUMNS] if not df.empty else pd.DataFrame(columns=STORE_COLUMNS)


def load_raw_context(errors: dict) -> RawContext:
    from macro_app.io import dulieukinhte_api, fred, vbma, vn_raw, westmetall, yahoo

    parts = [
        _safe_load("vn", lambda: vn_raw.load_vn_series(errors=errors), errors),
        _safe_load("fred", fred.load_fred_series, errors),
        _safe_load("yahoo", yahoo.load_yahoo_series, errors),
        _safe_load("vbma", vbma.load_vbma_series, errors),
        _safe_load("lme", westmetall.load_lme_series, errors),
    ]
    store = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    store["date"] = pd.to_datetime(store["date"]).dt.normalize()
    # số kéo qua API dulieukinhte đè số trong file Excel cùng chuỗi, cùng kỳ (bản mới thắng)
    api = _safe_load("dulieukinhte", dulieukinhte_api.load_series, errors)
    if not api.empty:
        api["date"] = pd.to_datetime(api["date"]).dt.normalize()
        store = dulieukinhte_api.overlay(store, api)
    store["value"] = pd.to_numeric(store["value"], errors="coerce")
    panel = banks = None
    try:
        panel, banks = vn_raw.load_deposit_panel(), vn_raw.load_banks()
    except Exception as exc:
        errors["deposit"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return RawContext(store=store, deposit_panel=panel, banks=banks, manual=manual_io.read_manual())


def cache_times() -> dict[str, str | None]:
    from macro_app.io.excel_cache import cache_fetched_at, read_cache

    out = {}
    for name in ("fred", "yahoo", "vbma", "fedwatch", "lme"):
        _, meta = read_cache(CACHE_DIR / f"{name}.xlsx")
        ts = cache_fetched_at(meta)
        out[name] = ts.isoformat() if ts is not None else None
    return out


def series_long(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    parts = [f.reset_index().assign(code=code) for code, f in frames.items() if not f.empty]
    if not parts:
        return pd.DataFrame(columns=["code", "date", "value", "source"])
    return pd.concat(parts, ignore_index=True)[["code", "date", "value", "source"]]


def build_latest(indicators, frames, ctx: RawContext, today: pd.Timestamp) -> pd.DataFrame:
    thresholds = cfgmod.load_thresholds()
    rules = cfgmod.load_impact_rules()
    params = cfgmod.load_app_params()
    rows = [
        summarize(
            ind,
            frames[ind.code],
            store=ctx.store,
            thresholds=thresholds,
            rules=rules,
            params=params,
            today=today,
            rebase_series=rebase_input(ind, ctx),
        )
        for ind in indicators
    ]
    return pd.DataFrame(rows)


def append_status_history(latest: pd.DataFrame, path: Path, run_at: str) -> pd.DataFrame:
    """Ghi 1 dòng/chỉ số mỗi lần build.

    reason = data (giá trị/kỳ đổi) | threshold (chỉ ngưỡng đổi).
    """
    cols = ["run_at", "code", "period", "value", "status", "reason"]
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=cols)
    last = old.drop_duplicates("code", keep="last").set_index("code") if not old.empty else None
    new = latest[["code", "period", "value", "status"]].copy()
    new["period"] = pd.to_datetime(new["period"]).dt.strftime("%Y-%m-%d")
    new["run_at"] = run_at

    def reason(row) -> str:
        if last is None or row["code"] not in last.index:
            return "data"
        prev = last.loc[row["code"]]
        same_data = str(prev["period"]) == str(row["period"]) and np.isclose(
            float(prev["value"]) if pd.notna(prev["value"]) else np.nan,
            float(row["value"]) if pd.notna(row["value"]) else np.nan,
            equal_nan=True,
        )
        return "threshold" if same_data and prev["status"] != row["status"] else "data"

    new["reason"] = new.apply(reason, axis=1)
    out = new[cols] if old.empty else pd.concat([old, new[cols]], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False, encoding="utf-8")
    return out


def write_public(indicators, frames, latest: pd.DataFrame, history: pd.DataFrame, vintage: str):
    series_dir = PUBLIC_DIR / "series"
    series_dir.mkdir(parents=True, exist_ok=True)
    by_code = {i.code: i for i in indicators}
    for code, frame in frames.items():
        ind = by_code[code]
        public = frame[~frame["source"].isin(VENDOR_SOURCES)].reset_index()
        if public.empty and (series_dir / f"{code}.csv").exists():
            continue  # nguồn lỗi lần này thì giữ file công khai lần trước
        public = public.assign(unit=ind.unit, frequency=ind.frequency, vintage_date=vintage)
        public["date"] = public["date"].dt.strftime("%Y-%m-%d")
        public[["date", "value", "unit", "source", "frequency", "vintage_date"]].to_csv(
            series_dir / f"{code}.csv", index=False, encoding="utf-8"
        )
    pub_latest = latest.copy()
    yahoo_rows = pub_latest["row_source"].isin(VENDOR_SOURCES)
    numeric = [
        "value",
        "prev_value",
        "change",
        "yoy_change",
        "ytd_change",
        "vs_target",
        "zscore_5y",
        "distance_to_next",
    ]
    pub_latest.loc[yahoo_rows, numeric] = np.nan
    pub_latest.loc[yahoo_rows, "flags"] += ";yahoo_hidden"
    pub_latest["build_date"] = vintage
    pub_latest.to_csv(PUBLIC_DIR / "latest.csv", index=False, encoding="utf-8")
    dictionary = pd.DataFrame(
        [
            {
                "code": i.code,
                "name_vi": i.name,
                "name_en": i.extra.get("name_en", ""),
                "group": i.group,
                "unit": i.unit,
                "frequency": i.frequency,
                "source": i.source,
                "source_url": i.source_url,
                "raw_input": str(i.recipe.get("input") or i.recipe.get("inputs")),
                "note": "; ".join(i.flags),
            }
            for i in indicators
        ]
    )
    dictionary.to_csv(PUBLIC_DIR / "dictionary.csv", index=False, encoding="utf-8")
    yahoo_codes = set(pub_latest.loc[yahoo_rows, "code"])
    pub_history = history.copy()
    pub_history.loc[pub_history["code"].isin(yahoo_codes), "value"] = np.nan
    pub_history.to_csv(PUBLIC_DIR / HISTORY_FILE, index=False, encoding="utf-8")


def scorecard_context(indicators, frames, ctx: RawContext, today: pd.Timestamp) -> dict:
    """Ngữ cảnh chấm scorecard từ store raw (mục tiêu Chính phủ lấy từ file 28.1)."""
    from macro_app.metrics import scorecard as sc

    store = ctx.store
    wanted = {i.target for i in indicators if i.target}
    target_series = {
        sid: pd.Series(g["value"].to_numpy(), index=pd.DatetimeIndex(g["date"])).sort_index()
        for sid, g in store[store["series_id"].isin(wanted)].groupby("series_id")
    }
    catalog = {i.code: i for i in indicators}
    default, _ = cfgmod.load_thresholds()
    return sc.make_context(
        frames,
        catalog,
        target_series,
        asof=today,
        settings=sc.load_settings(),
        min_points=default["min_points"],
    )


def vendor_codes(frames: dict[str, pd.DataFrame]) -> set[str]:
    """Mã có số liệu của nguồn có giấy phép (Yahoo, LME) ở bất kỳ kỳ nào."""
    return {
        code
        for code, frame in frames.items()
        if not frame.empty and frame["source"].isin(VENDOR_SOURCES).any()
    }


def build_scorecards(
    indicators, frames, ctx: RawContext, errors: dict, today: pd.Timestamp
) -> None:
    """Ghi điểm hiện tại + lịch sử của mọi phân khúc, mọi bộ cấu hình vào data/app, data/public."""
    from macro_app import profiles
    from macro_app.metrics import scorecard as sc

    catalog = {i.code: i for i in indicators}
    sctx = scorecard_context(indicators, frames, ctx, today)
    prev_month = today + pd.offsets.MonthEnd(0) - pd.offsets.MonthEnd(1)
    rows, totals, hist = [], [], []
    for pslug, prof in profiles.load_profiles().items():
        for slug, card in prof["segments"].items():
            key = f"scorecard:{pslug}/{slug}"
            problems = sc.validate_card(card, catalog, sctx["settings"])
            if problems:
                errors[key] = "; ".join(problems)[:300]
            try:
                table, total = sc.current(card, frames, catalog, sctx)
                h = sc.history(card, frames, catalog, sctx)
            except Exception as exc:
                errors[key] = f"{type(exc).__name__}: {str(exc)[:200]}"
                continue
            tag = {"profile": pslug, "segment": slug}
            rows.append(table.assign(**tag))
            hist.append(h.assign(**tag))
            totals.append(
                {
                    **tag,
                    "profile_name": prof["name"],
                    "name": card["name"],
                    **sc.summarize_total(total, h, table, prev_month),
                }
            )
    if not totals:
        return
    outputs = {
        "scorecard_rows": pd.concat(rows, ignore_index=True),
        "scorecard_totals": pd.DataFrame(totals),
        "scorecard_history": pd.concat(hist, ignore_index=True),
    }
    vendor = vendor_codes(frames)
    for name, df in outputs.items():
        df.to_parquet(APP_DIR / f"{name}.parquet", index=False)
        public = df
        if name == "scorecard_rows":  # số đã đo và diễn giải của dòng vendor không ra bản công khai
            public = df.copy()
            hidden = public["code"].isin(vendor)
            public.loc[hidden, ["measured", "detail"]] = [np.nan, ""]
        public.to_csv(PUBLIC_DIR / f"{name}.csv", index=False, encoding="utf-8")


def run_build(today: pd.Timestamp | None = None) -> dict:
    today = (today or pd.Timestamp.now()).normalize()
    run_at = datetime.now().replace(microsecond=0).isoformat()
    errors: dict[str, str] = {}
    indicators = cfgmod.load_catalog()
    ctx = load_raw_context(errors)
    frames = compute_all(indicators, ctx)
    latest = build_latest(indicators, frames, ctx, today)

    APP_DIR.mkdir(parents=True, exist_ok=True)
    targets = ctx.store[ctx.store["series_id"].isin(cfgmod.load_targets())]
    targets = targets.rename(columns={"series_id": "code"})[["code", "date", "value", "source"]]
    pd.concat([series_long(frames), targets], ignore_index=True).to_parquet(
        APP_DIR / "series.parquet", index=False
    )
    export_fedwatch(errors)
    latest.to_parquet(APP_DIR / "latest.parquet", index=False)
    history = append_status_history(latest, APP_DIR / HISTORY_FILE, run_at)
    write_public(indicators, frames, latest, history, today.strftime("%Y-%m-%d"))
    build_scorecards(indicators, frames, ctx, errors, today)
    ctx.store.to_parquet(APP_DIR / RAW_STORE_FILE, index=False)

    meta = {
        "built_at": run_at,
        "today": today.strftime("%Y-%m-%d"),
        "n_indicators": len(indicators),
        "n_with_data": int(latest["value"].notna().sum()),
        "cache_fetched_at": cache_times(),
        "source_errors": errors,
        "raw_modified": raw_modified_times(),
    }
    (APP_DIR / "build_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


def export_fedwatch(errors: dict) -> None:
    """Chép các bảng FedWatch từ cache Excel sang parquet cho app đọc nhanh."""
    try:
        from macro_app.io.fedwatch import load_fedwatch

        tables = load_fedwatch(CACHE_DIR / "fedwatch.xlsx")
    except Exception as exc:
        errors["fedwatch"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return
    for name in ("computed", "quikstrike", "fomc_calendar"):
        df = tables.get(name)
        if df is not None and not df.empty:
            df.to_parquet(APP_DIR / f"fedwatch_{name}.parquet", index=False)


def rescore(today: pd.Timestamp | None = None) -> dict:
    """Tính lại trạng thái và scorecard từ dữ liệu đã build (dùng khi chỉ đổi ngưỡng/scorecard).

    Không đọc lại file raw. Chưa có bản build nào thì chạy build đầy đủ.
    """
    series_path, store_path = APP_DIR / "series.parquet", APP_DIR / RAW_STORE_FILE
    if not series_path.exists() or not store_path.exists():
        return run_build(today)
    today = (today or pd.Timestamp.now()).normalize()
    run_at = datetime.now().replace(microsecond=0).isoformat()
    indicators = cfgmod.load_catalog()
    long = pd.read_parquet(series_path)
    long["date"] = pd.to_datetime(long["date"])
    codes = {i.code for i in indicators}
    frames = {
        code: g.set_index("date")[["value", "source"]].sort_index()
        for code, g in long[long["code"].isin(codes)].groupby("code")
    }
    frames.update(
        {
            i.code: pd.DataFrame(columns=["value", "source"])
            for i in indicators
            if i.code not in frames
        }
    )
    ctx = RawContext(store=pd.read_parquet(store_path))
    errors: dict[str, str] = {}
    latest = build_latest(indicators, frames, ctx, today)
    latest.to_parquet(APP_DIR / "latest.parquet", index=False)
    history = append_status_history(latest, APP_DIR / HISTORY_FILE, run_at)
    write_public(indicators, frames, latest, history, today.strftime("%Y-%m-%d"))
    build_scorecards(indicators, frames, ctx, errors, today)
    meta_path = APP_DIR / "build_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta["rescored_at"] = run_at
    kept = {
        k: v for k, v in meta.get("source_errors", {}).items() if not k.startswith("scorecard:")
    }
    meta["source_errors"] = {**kept, **errors}
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def raw_modified_times() -> dict[str, str]:
    from macro_app.paths import RAW_DIR

    return {
        p.name: datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        for p in sorted(RAW_DIR.glob("*"))
        if p.is_file() and p.suffix in (".xlsx", ".csv", ".json")
    }
