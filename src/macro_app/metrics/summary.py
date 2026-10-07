"""Một dòng tổng hợp cho mỗi chỉ số (giá trị, thay đổi, trạng thái, tác động, cờ) của latest.csv."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from macro_app.config import Indicator
from macro_app.metrics import impact as imp
from macro_app.metrics import transforms as tf
from macro_app.metrics.quality import quality_flags
from macro_app.metrics.status import INSUFFICIENT, evaluate, resolve_threshold

UNIT_TEXT = {
    "period": {"D": "ngày", "W": "tuần", "M": "tháng", "Q": "quý", "A": "năm"},
    "day": "ngày",
    "year": "năm",
}


def measure_text(spec: dict | None, frequency: str) -> str:  # noqa: PLR0911
    """Mô tả ngắn cách đo, vd '% thay đổi so 3 tháng trước'."""
    spec = spec or {}
    kind = spec.get("kind", "level")
    if kind == "level":
        return ""
    if kind == "ytd_change":
        return "thay đổi từ đầu năm"
    if kind == "ytd_pct":
        return "% thay đổi từ đầu năm"
    if kind == "sum12_pct":
        return "tổng 12 tháng, % so cùng kỳ"
    if kind == "mean":
        n, unit = int(spec.get("n", 1)), spec.get("unit", "period")
        word = UNIT_TEXT["period"].get(frequency, "kỳ") if unit == "period" else "ngày"
        return f"trung bình {n} {word}"
    unit = spec.get("unit", "period")
    unit_word = UNIT_TEXT["period"].get(frequency, "kỳ") if unit == "period" else UNIT_TEXT[unit]
    n = int(spec.get("n", 1))
    when = "cùng kỳ năm trước" if unit == "year" and n == 1 else f"{n} {unit_word} trước"
    return ("% thay đổi" if kind == "pct_change" else "thay đổi") + f" so {when}"


def target_for(ind: Indicator, store: pd.DataFrame, latest_date: pd.Timestamp) -> float:
    """Mục tiêu Chính phủ của năm chứa kỳ mới nhất (file 28.1)."""
    if not ind.target or pd.isna(latest_date):
        return np.nan
    part = store[(store["series_id"] == ind.target) & (store["date"].dt.year == latest_date.year)]
    return float(part["value"].iloc[-1]) if not part.empty else np.nan


def summarize(  # noqa: PLR0913
    ind: Indicator,
    frame: pd.DataFrame,
    *,
    store: pd.DataFrame,
    thresholds: tuple[dict, dict],
    rules: dict,
    params: dict,
    today: pd.Timestamp,
    rebase_series: pd.Series | None,
) -> dict:
    s = frame["value"] if not frame.empty else pd.Series(dtype=float)
    latest_date = s.index[-1] if len(s) else pd.NaT
    latest = float(s.iloc[-1]) if len(s) else np.nan
    prev_date, prev = tf.previous_value(s, ind.frequency, params["change"]["daily_window_days"])
    target = target_for(ind, store, latest_date)
    yoy = tf.change(latest, tf.same_period_last_year(s, ind.frequency), ind.change_unit)
    ytd = tf.change(latest, tf.last_value_prev_year(s), ind.change_unit)

    default, overrides = thresholds
    cfg, cfg_source = resolve_threshold(ind.code, default, overrides)
    status = evaluate(s, ind.frequency, cfg, cfg_source, target)
    is_ytd = "ytd" in ind.flags  # lũy kế reset mỗi tháng 1 nên so cùng kỳ
    trend_fn = imp.trend_vs_last_year if is_ytd else imp.trend
    trend_dir, _ = trend_fn(s, ind.frequency, params["trend"])
    group_rule = rules["groups"].get(ind.group)
    sign = int(ind.extra.get("impact_sign", 1))
    cells = imp.group_cells(group_rule, imp.apply_sign(trend_dir, sign)) if sign else None

    min_points = int(default["min_points"][ind.frequency])
    flags = quality_flags(
        series=s,
        frequency=ind.frequency,
        catalog_flags=ind.flags,
        today=today,
        params=params["quality"],
        min_points=min_points,
        rebase_input=rebase_series,
    )
    if "rebase_suspect" in flags:
        status = replace(status, status=INSUFFICIENT, detail="Nghi đổi năm gốc, chưa xếp màu")
    if cfg_source == "default":
        flags.append("default_threshold")
    if ind.manual and not frame.empty:
        last_src = frame["source"].iloc[-1]
        flags.append("ai_suggested_confirmed" if last_src.startswith("AI") else "manual")

    row = {
        "code": ind.code,
        "name": ind.name,
        "group": ind.group,
        "block": ind.block,
        "unit": ind.unit,
        "frequency": ind.frequency,
        "period": latest_date,
        "value": latest,
        "prev_period": prev_date,
        "prev_value": prev,
        "change": yoy if is_ytd else tf.change(latest, prev, ind.change_unit),
        "change_basis": "yoy" if is_ytd else ("30d" if ind.frequency == "D" else "prev"),
        "change_unit": ind.change_unit,
        "yoy_change": yoy,
        "ytd_change": np.nan if is_ytd else ytd,
        "target": target,
        "vs_target": latest - target if not np.isnan(target) else np.nan,
        "zscore_5y": tf.zscore_latest(s, 5, min_points),
        "status": status.status,
        "threshold_method": status.method,
        "threshold_source": status.threshold_source,
        "threshold_note": cfg.get("description", "") or "",
        "threshold_detail": status.detail,
        "status_label": status.label,
        "measure": measure_text(cfg.get("measure"), ind.frequency),
        "distance_to_next": status.distance_to_next,
        "trend": trend_dir,
        "favorability": imp.favorability(ind.direction, trend_dir),
        "direction": ind.direction,
        "segment": ind.segment,
        "flags": ";".join(flags),
        "source": ind.source,
        "row_source": frame["source"].iloc[-1] if not frame.empty else "",
        "source_url": ind.source_url,
    }
    for cell in imp.CELLS:
        row[f"impact_{cell}"] = cells[cell] if cells else ""
    return row
