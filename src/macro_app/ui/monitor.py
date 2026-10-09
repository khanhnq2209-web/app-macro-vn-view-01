"""Bảng theo dõi trang Tổng quan: mỗi chỉ số một dòng, gom theo nhóm."""

from __future__ import annotations

import base64
import html
from dataclasses import dataclass

import numpy as np
import pandas as pd

from macro_app import fmt
from macro_app.charts import theme as t

SPARK_W, SPARK_H = 84, 24
BASIS = {"yoy": "so cùng kỳ", "30d": "so 30 ngày", "prev": "so kỳ trước"}
COLS = (
    '<colgroup><col><col style="width:90px"><col style="width:108px">'
    '<col style="width:96px"></colgroup>'
)


@dataclass(frozen=True)
class BlockContext:
    sparks: dict[str, pd.Series]
    decimals: dict[str, int]
    group_names: dict[str, str]


def spark_points(s: pd.Series, frequency: str) -> pd.Series:
    """Ngày/tuần: 1 năm (ngày gộp theo tuần). Tháng 24, quý 12, năm 10 điểm."""
    s = s.dropna()
    if s.empty:
        return s
    if frequency in ("D", "W"):
        s = s[s.index > s.index[-1] - pd.DateOffset(years=1)]
        return s.resample("W").last().dropna() if frequency == "D" else s
    return s.tail({"M": 24, "Q": 12, "A": 10}.get(frequency, 24))


def sparkline(s: pd.Series, status: str | None = None) -> str:
    """SVG nhúng dạng data URI vì st.html bỏ thẻ <svg>. Có status (Scorecard) thì chấm cuối tô màu mức."""
    if len(s) < 2:
        return ""
    y = s.to_numpy(dtype=float)
    lo, hi = np.nanmin(y), np.nanmax(y)
    span = (hi - lo) or 1.0
    xs = np.linspace(2, SPARK_W - 4, len(y))
    ys = SPARK_H - 3 - (y - lo) / span * (SPARK_H - 6)
    pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(xs, ys, strict=True))
    dot = t.STATUS_COLORS.get(status, t.STATUS_COLORS["none"])[1] if status else t.MUTED
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SPARK_W}" height="{SPARK_H}">'
        f'<polyline points="{pts}" fill="none" stroke="{t.MUTED}" stroke-width="1.4" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="2.6" fill="{dot}"/></svg>'
    )
    data = base64.b64encode(svg.encode()).decode()
    return (
        f'<img alt="" width="{SPARK_W}" height="{SPARK_H}" src="data:image/svg+xml;base64,{data}">'
    )


def _value(value, unit: str, decimals: int) -> str:
    if pd.isna(value):
        return '<span class="mv-empty">chưa có số</span>'
    if unit == "%":
        return f'<span class="mv-num">{fmt.number(value, decimals)}%</span>'
    return (
        f'<span class="mv-num">{fmt.number(value, decimals)}</span>'
        f'<span class="mv-unit">{html.escape(unit)}</span>'
    )


def _change(row: pd.Series) -> str:
    if pd.isna(row["value"]) or pd.isna(row.get("change")):
        return ""
    basis = BASIS.get(row.get("change_basis"), "")
    return f'{fmt.change(row["change"], row["change_unit"])}<span class="mv-basis">{basis}</span>'


def row_html(row: pd.Series, spark: pd.Series, decimals: int) -> str:
    name = html.escape(row["name"])
    meta = f"{fmt.period(row['period'], row['frequency'])} · {html.escape(row['source'])}"
    return (
        "<tr>"
        f'<td class="mv-name"><a href="detail?code={row["code"]}" target="_self" title="{name}">'
        f'{name}</a><div class="mv-meta">{meta}</div></td>'
        f'<td class="mv-spark m-hide">{sparkline(spark)}</td>'
        f'<td class="mv-val">{_value(row["value"], row["unit"], decimals)}</td>'
        f'<td class="mv-chg">{_change(row)}</td>'
        "</tr>"
    )


def block_html(title: str, rows: pd.DataFrame, ctx: BlockContext) -> str:
    head = (
        '<tr><th></th><th class="m-hide">Xu hướng</th><th class="r">Giá trị</th>'
        '<th class="r">Thay đổi</th></tr>'
    )
    body = []
    for group, part in rows.groupby("group", sort=False):
        label = html.escape(ctx.group_names.get(group, group))
        body.append(
            f'<tr class="mv-group"><td colspan="3">{label}</td><td class="m-hide"></td></tr>'
        )
        body += [
            row_html(r, ctx.sparks[r["code"]], ctx.decimals[r["code"]]) for _, r in part.iterrows()
        ]
    return (
        f'<div class="mv-title">{html.escape(title)}</div>'
        f'<table class="mv">{COLS}{head}{"".join(body)}</table>'
    )
