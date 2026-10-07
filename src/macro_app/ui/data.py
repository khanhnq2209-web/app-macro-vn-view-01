"""Đọc data/app/ cho app. Cache theo mtime file build nên build mới tự làm mới cache."""

from __future__ import annotations

import json
import os

import pandas as pd
import streamlit as st

from macro_app import config as cfgmod
from macro_app.metrics import forward as fw
from macro_app.paths import APP_DIR, CONFIG_DIR


def build_stamp() -> float:
    meta = APP_DIR / "build_meta.json"
    return meta.stat().st_mtime if meta.exists() else 0.0


@st.cache_data(show_spinner=False)
def _latest(stamp: float) -> pd.DataFrame:
    path = APP_DIR / "latest.parquet"
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


@st.cache_data(show_spinner=False)
def _series(stamp: float) -> pd.DataFrame:
    path = APP_DIR / "series.parquet"
    if not path.exists():
        return pd.DataFrame(columns=["code", "date", "value", "source"])
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data(show_spinner=False)
def _history(stamp: float) -> pd.DataFrame:
    path = APP_DIR / "status_history.csv"
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


@st.cache_data(show_spinner=False)
def _fedwatch(stamp: float) -> dict[str, pd.DataFrame]:
    out = {}
    for name in ("computed", "quikstrike", "fomc_calendar"):
        path = APP_DIR / f"fedwatch_{name}.parquet"
        if path.exists():
            out[name] = pd.read_parquet(path)
    return out


def _setting(name: str) -> str:
    try:
        if name in st.secrets:
            return str(st.secrets.get(name, ""))
    except FileNotFoundError:
        pass
    return os.getenv(name, "")


def hide_vendor() -> bool:
    """Ẩn số Yahoo, LME (giấy phép) ở bản deploy.

    APP_MODE=admin luôn hiện. Bản nội bộ bật SHOW_VENDOR_DATA=1; người bật chịu trách nhiệm điều khoản.
    """
    if _setting("APP_MODE").lower() == "admin":
        return False
    return _setting("SHOW_VENDOR_DATA").strip().lower() not in ("1", "true", "yes")


VENDOR_SOURCES = ("Yahoo", "LME (Westmetall)")
VENDOR_COLUMNS = [
    "value",
    "prev_value",
    "change",
    "yoy_change",
    "ytd_change",
    "vs_target",
    "zscore_5y",
    "distance_to_next",
]


def latest() -> pd.DataFrame:
    df = _latest(build_stamp())
    if hide_vendor() and not df.empty:
        df = df.copy()
        vendor = df["row_source"].isin(VENDOR_SOURCES)
        df.loc[vendor, VENDOR_COLUMNS] = float("nan")
        df.loc[vendor, "status"] = "no_data"
        df.loc[vendor, "flags"] = df.loc[vendor, "flags"].fillna("") + ";vendor_hidden"
    return df


def series(code: str) -> pd.Series:
    part = series_frame(code)
    return pd.Series(part["value"].to_numpy(), index=pd.DatetimeIndex(part["date"]), name=code)


def series_frame(code: str) -> pd.DataFrame:
    df = _series(build_stamp())
    part = df[df["code"] == code].drop(columns="code")
    return part[~part["source"].isin(VENDOR_SOURCES)] if hide_vendor() else part


def history() -> pd.DataFrame:
    return _history(build_stamp())


def fedwatch() -> dict[str, pd.DataFrame]:
    return _fedwatch(build_stamp())


def build_meta() -> dict:
    path = APP_DIR / "build_meta.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


@st.cache_data(show_spinner=False)
def catalog_map(_stamp: float = 0.0) -> dict:
    return {i.code: i for i in cfgmod.load_catalog()}


@st.cache_data(show_spinner=False)
def _impact_rules(stamp: float) -> dict:
    return cfgmod.load_impact_rules()


def impact_rules() -> dict:
    return _impact_rules(build_stamp())


@st.cache_data(show_spinner=False)
def target_series(target_id: str, stamp: float) -> pd.Series:
    """Chuỗi mục tiêu Chính phủ theo năm, lưu trong series.parquet dưới mã target."""
    df = _series(stamp)
    part = df[df["code"] == target_id]
    return pd.Series(part["value"].to_numpy(), index=pd.DatetimeIndex(part["date"]))


@st.cache_data(show_spinner=False)
def _scorecard(name: str, stamp: float) -> pd.DataFrame:
    path = APP_DIR / f"scorecard_{name}.parquet"
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def scorecard_rows() -> pd.DataFrame:
    return _scorecard("rows", build_stamp())


def scorecard_totals() -> pd.DataFrame:
    return _scorecard("totals", build_stamp())


def scorecard_history() -> pd.DataFrame:
    df = _scorecard("history", build_stamp())
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data(show_spinner=False)
def _scorecard_inputs(stamp: float) -> tuple[dict, dict]:
    long = _series(stamp)
    frames = {c: g.set_index("date")[["value"]].sort_index() for c, g in long.groupby("code")}
    targets = {c: f["value"] for c, f in frames.items() if c.startswith("vn.target_")}
    return frames, targets


def _config_stamp() -> tuple:
    """Khóa cache: ngày chấm và mtime các file cấu hình ảnh hưởng điểm."""
    names = ("scorecard.yaml", "thresholds.default.yaml", "catalog.yaml", "forecast_map.yaml")
    mtimes = tuple((CONFIG_DIR / n).stat().st_mtime for n in names)
    return (str(pd.Timestamp.now().normalize().date()), *mtimes)


def scorecard_eval(card_json: str, stamp: float) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Chấm một phân khúc. Bản công khai che số đo của dòng vendor."""
    table, total, hist = _scorecard_eval(card_json, stamp, _config_stamp())
    if hide_vendor() and not table.empty:
        vendor = latest().set_index("code")["row_source"].isin(VENDOR_SOURCES)
        hidden = table["code"].isin(vendor.index[vendor])
        table = table.copy()
        table.loc[hidden, ["measured", "detail"]] = [float("nan"), ""]
    return table, total, hist


@st.cache_data(show_spinner="Đang chấm điểm…")
def _scorecard_eval(
    card_json: str, stamp: float, config_stamp: tuple
) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    from macro_app.metrics import scorecard as sc

    card = json.loads(card_json)
    frames, targets = _scorecard_inputs(stamp)
    catalog = catalog_map()
    ctx = sc.make_context(
        frames,
        catalog,
        targets,
        asof=pd.Timestamp.now().normalize(),
        settings=sc.load_settings(),
        min_points=cfgmod.load_thresholds()[0]["min_points"],
    )
    table, total, hist = sc.evaluate_card(card, frames, catalog, ctx)
    # Điểm theo dự báo chỉ để tham khảo, không vào điểm chính.
    path = fw.fed_path(fw.pick_fedwatch({k: v.copy() for k, v in _fedwatch(stamp).items()}))
    table, fwd_score = fw.annotate(
        table,
        card,
        frames=frames,
        catalog=catalog,
        path=path,
        ctx={**ctx, "target_series_by_id": targets, "forecast_map": fw.load_forecast_map()},
    )
    total["fwd_score"] = fwd_score
    total["fwd_rating"] = sc.rating(fwd_score, ctx["settings"]["rating_bands"])
    if not hist.empty:
        hist["date"] = pd.to_datetime(hist["date"])
    return table, total, hist


def fed_path() -> pd.DataFrame:
    return fw.fed_path(fw.pick_fedwatch({k: v.copy() for k, v in fedwatch().items()}))


def forecast_overview(mappings: list[dict]) -> pd.DataFrame:
    """Mỗi dòng: số thực tế mới nhất, kế hoạch / dự báo chính, chênh lệch, các điểm khác."""
    stamp = build_stamp()
    frames, targets = _scorecard_inputs(stamp)
    catalog = catalog_map()
    path = fw.fed_path(fw.pick_fedwatch({k: v.copy() for k, v in _fedwatch(stamp).items()}))
    asof = pd.Timestamp.now().normalize()
    target_ids = set(targets)
    rows = []
    for m in mappings:
        errors = fw.validate_mapping(m, catalog, target_ids)
        code = m.get("code")
        ind = catalog.get(code)
        frame = frames.get(code)
        s = (
            frame["value"].dropna()
            if frame is not None and not frame.empty
            else pd.Series(dtype=float)
        )
        pts = (
            [] if errors else fw.points_for(m, path=path, targets=targets, frames=frames, asof=asof)
        )
        main = fw.primary(pts, asof)
        actual = float(s.iloc[-1]) if len(s) else float("nan")
        rows.append(
            {
                "code": code,
                "name": ind.name if ind else str(code),
                "unit": ind.unit if ind else "",
                "frequency": ind.frequency if ind else "",
                "direction": ind.direction if ind else "",
                "actual": actual,
                "actual_date": s.index[-1] if len(s) else pd.NaT,
                "kind": m.get("kind"),
                "label": m.get("label") or fw.KIND_LABEL.get(m.get("kind"), ""),
                "plan": main.value if main else float("nan"),
                "plan_when": main.label if main else "",
                "plan_source": main.source if main else "",
                "others": " · ".join(f"{p.label}: {p.value:.2f}" for p in pts),
                "change": (main.value - actual) if main and len(s) else float("nan"),
                "note": m.get("note") or "",
                "error": "; ".join(errors),
            }
        )
    return pd.DataFrame(rows)
