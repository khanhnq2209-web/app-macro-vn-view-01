"""Chart chuỗi thời gian cho trang Quốc tế / Việt Nam / Chi tiết. Không import streamlit."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from macro_app.charts import theme
from macro_app.metrics import transforms as tf

RANGE_YEARS = {"1Y": 1, "3Y": 3, "5Y": 5, "10Y": 10, "ALL": None}
TRANSFORM_LABEL = {
    "level": "Mức",
    "yoy": "So cùng kỳ",
    "ytd": "Từ đầu năm",
    "zscore": "Z-score 5 năm",
}


@dataclass
class SeriesSpec:
    code: str
    name: str
    unit: str
    frequency: str
    change_unit: str
    values: pd.Series
    secondary: bool = False


@dataclass
class ChartSpec:
    title: str
    series: list[SeriesSpec]
    kind: str = "line"  # line | bar | area
    range: str = "5Y"
    transform: str = "level"
    target: pd.Series | None = None  # đường mục tiêu (bậc thang theo năm)
    bands: dict = field(
        default_factory=dict
    )  # {"green": [[lo, hi]], "yellow": [[lo, hi]]}, ngưỡng tuyệt đối
    note: str = ""


def transform_series(s: SeriesSpec, how: str) -> tuple[pd.Series, str]:  # noqa: PLR0911
    """Trả (chuỗi đã biến đổi, nhãn đơn vị trục y)."""
    v = tf.clean(s.values)
    if how == "level" or v.empty:
        return v, s.unit
    if how == "zscore":
        return tf.rolling_zscore(v, 5, 24 if s.frequency in "MDW" else 8).dropna(), "z"
    if how == "yoy":
        if s.change_unit == "pct":
            return tf.yoy_pct(v, s.frequency).dropna(), "% so cùng kỳ"
        if s.frequency not in ("D", "W"):  # lưới kỳ đều: shift theo lịch để kỳ thiếu ra NaN
            v = tf.to_period(v, s.frequency)
        prev = (
            tf.value_year_ago(v)
            if s.frequency in ("D", "W")
            else v.shift(tf.PERIODS_PER_YEAR[s.frequency])
        )
        return (v - prev).dropna(), "điểm % so cùng kỳ"
    if how == "ytd":
        if s.change_unit == "pct":
            return tf.ytd_change_pct(v).dropna(), "% từ đầu năm"
        year_end = v.groupby(v.index.year).last()
        base = pd.Series(v.index.year - 1, index=v.index).map(year_end)
        return (v - base).dropna(), "điểm % từ đầu năm"
    raise ValueError(f"transform không hỗ trợ: {how}")


def clip_range(s: pd.Series, rng: str) -> pd.Series:
    years = RANGE_YEARS.get(rng)
    if years is None or s.empty:
        return s
    return s[s.index >= s.index.max() - pd.DateOffset(years=years)]


def _trace(  # noqa: PLR0913, PLR0917
    kind: str,
    x,
    y,
    name: str,
    color: str,
    secondary: bool,  # noqa: FBT001
    hover_unit: str,
) -> go.BaseTraceType:
    common = {
        "x": x,
        "y": y,
        "name": name,
        "hovertemplate": f"%{{y:,.2f}} {hover_unit}<extra>{name}</extra>",
    }
    if secondary:
        common["yaxis"] = "y2"
    if kind == "bar":
        return go.Bar(**common, marker_color=color)
    fill = "tozeroy" if kind == "area" else None
    return go.Scatter(**common, mode="lines", line={"color": color, "width": 2}, fill=fill)


def _add_bands(fig: go.Figure, bands: dict, y_min: float, y_max: float) -> None:
    """Tô nền vùng vàng/đỏ cho ngưỡng absolute: ngoài khoảng xanh và vàng là đỏ."""
    yellow_bg = theme.STATUS_COLORS["yellow"][0]
    for lo, hi in bands.get("yellow") or []:
        fig.add_hrect(
            y0=lo if lo is not None else y_min,
            y1=hi if hi is not None else y_max,
            fillcolor=yellow_bg,
            opacity=0.6,
            line_width=0,
            layer="below",
        )
    ok = sorted(
        [r for key in ("green", "yellow") for r in (bands.get(key) or [])],
        key=lambda r: -np.inf if r[0] is None else r[0],
    )
    red_bg = theme.STATUS_COLORS["red"][0]
    lows = [r[0] for r in ok if r[0] is not None]
    highs = [r[1] for r in ok if r[1] is not None]
    if lows and min(lows) > y_min:
        fig.add_hrect(
            y0=y_min, y1=min(lows), fillcolor=red_bg, opacity=0.6, line_width=0, layer="below"
        )
    if highs and max(highs) < y_max:
        fig.add_hrect(
            y0=max(highs), y1=y_max, fillcolor=red_bg, opacity=0.6, line_width=0, layer="below"
        )


def build_chart(spec: ChartSpec) -> go.Figure:
    fig = go.Figure()
    y_units = []
    all_y = []
    for i, s in enumerate(spec.series):
        values, unit = transform_series(s, spec.transform)
        values = clip_range(values, spec.range)
        color = theme.CATEGORICAL[i % len(theme.CATEGORICAL)]
        fig.add_trace(
            _trace(spec.kind, values.index, values.to_numpy(), s.name, color, s.secondary, unit)
        )
        if not s.secondary:
            y_units.append(unit)
            all_y.extend(values.to_numpy().tolist())
    if spec.target is not None and spec.transform == "level" and not spec.target.empty:
        target = clip_range(tf.clean(spec.target), spec.range)
        fig.add_trace(
            go.Scatter(
                x=target.index,
                y=target.to_numpy(),
                name="Mục tiêu",
                mode="lines",
                line={"color": theme.TARGET_LINE, "width": 2, "dash": "dash", "shape": "hv"},
            )
        )
    if spec.bands and spec.transform == "level" and all_y:
        span = (max(all_y) - min(all_y)) or 1.0
        _add_bands(fig, spec.bands, min(all_y) - 0.1 * span, max(all_y) + 0.1 * span)
    y_title = y_units[0] if len(set(y_units)) == 1 else " / ".join(sorted(set(y_units)))
    theme.apply_theme(fig, spec.title, y_title)
    if any(s.secondary for s in spec.series):
        fig.update_layout(yaxis2={"overlaying": "y", "side": "right", "showgrid": False})
    if not all_y:
        fig.add_annotation(
            text="Chưa có dữ liệu", showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper"
        )
    return fig
