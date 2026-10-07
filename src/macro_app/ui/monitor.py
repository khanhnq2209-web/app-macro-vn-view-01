"""Bảng theo dõi ở trang Tổng quan: mỗi chỉ số một dòng, gom theo nhóm.

Bấm tên chỉ số để mở trang chi tiết (?code=...).
"""

from __future__ import annotations

import base64
import html
from dataclasses import dataclass

import numpy as np
import pandas as pd

from macro_app import fmt
from macro_app.charts import theme as t
from macro_app.metrics.impact import TAG_LABEL
from macro_app.metrics.quality import FLAG_ICON, FLAG_LABEL
from macro_app.metrics.status import STATUS_LABEL

SPARK_W, SPARK_H = 84, 24
# Cờ có ở mọi dòng thì không cần lặp lại icon
HIDDEN_FLAGS = {"default_threshold"}
BASIS = {"yoy": "so cùng kỳ", "30d": "so 30 ngày", "prev": "so kỳ trước"}
FAV_GLYPH = {"favorable": "▲", "unfavorable": "▼", "two_way": "◆", "neutral": "●"}
FAV_COLOR = {
    "favorable": "#1F5FAE",
    "unfavorable": "#B3261E",
    "two_way": "#9A6700",
    "neutral": t.MUTED,
}
COLS = (
    '<colgroup><col style="width:16px"><col><col style="width:90px"><col style="width:108px">'
    '<col style="width:80px"><col style="width:34px"><col style="width:66px"></colgroup>'
)


@dataclass(frozen=True)
class BlockContext:
    sparks: dict[str, pd.Series]  # mã → chuỗi vẽ sparkline
    decimals: dict[str, int]
    symbols: dict[str, str]  # up/down/both/none → ↑ ↓ ⇅ ●
    group_names: dict[str, str]


def spark_points(s: pd.Series, frequency: str) -> pd.Series:
    """Một năm gần nhất với chuỗi ngày/tuần (ngày gộp theo tuần); 24 tháng, 12 quý, 10 năm."""
    s = s.dropna()
    if s.empty:
        return s
    if frequency in ("D", "W"):
        s = s[s.index > s.index[-1] - pd.DateOffset(years=1)]
        return s.resample("W").last().dropna() if frequency == "D" else s
    return s.tail({"M": 24, "Q": 12, "A": 10}.get(frequency, 24))


def sparkline(s: pd.Series, status: str) -> str:
    """Ảnh SVG nhúng dạng data URI (st.html không giữ thẻ <svg> trực tiếp)."""
    if len(s) < 2:
        return ""
    y = s.to_numpy(dtype=float)
    lo, hi = np.nanmin(y), np.nanmax(y)
    span = (hi - lo) or 1.0
    xs = np.linspace(2, SPARK_W - 4, len(y))
    ys = SPARK_H - 3 - (y - lo) / span * (SPARK_H - 6)
    pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(xs, ys, strict=True))
    dot = t.STATUS_COLORS.get(status, t.STATUS_COLORS["none"])[1]
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


def _impacts(row: pd.Series, symbols: dict) -> str:
    def pair(prefix: str, label: str) -> str:
        d, s = row.get(f"impact_{prefix}_demand"), row.get(f"impact_{prefix}_supply")
        if not d:
            return '<span class="mv-imp mv-muted">–</span>'
        marks = "".join(
            f'<b style="color:{t.IMPACT_COLORS[v][1]}">{symbols[v]}</b>' for v in (d, s)
        )
        return f'<span class="mv-imp" title="{label}: cầu, cung">{marks}</span>'

    return pair("housing", "Nhà ở") + pair("industrial", "KCN")


def _flags(flags: str) -> str:
    items = [f for f in str(flags or "").split(";") if f in FLAG_ICON and f not in HIDDEN_FLAGS]
    return "".join(
        f'<span title="{html.escape(FLAG_LABEL[f])}">{FLAG_ICON[f]}</span>' for f in items
    )


def row_html(row: pd.Series, spark: pd.Series, symbols: dict, decimals: int) -> str:
    status = row["status"]
    dot = t.STATUS_COLORS.get(status, t.STATUS_COLORS["none"])[1]
    has_value = pd.notna(row["value"])
    fav = row["favorability"] if has_value else "neutral"
    name = html.escape(row["name"])
    meta = f"{fmt.period(row['period'], row['frequency'])} · {html.escape(row['source'])}"
    return (
        "<tr>"
        f'<td class="mv-dot"><span style="background:{dot}" '
        f'title="{dot_title(row)}"></span></td>'
        f'<td class="mv-name"><a href="detail?code={row["code"]}" target="_self" title="{name}">'
        f'{name}</a><div class="mv-meta">{meta} {_flags(row["flags"])}</div></td>'
        f'<td class="mv-spark">{sparkline(spark, status)}</td>'
        f'<td class="mv-val">{_value(row["value"], row["unit"], decimals)}</td>'
        f'<td class="mv-chg">{_change(row)}</td>'
        f'<td class="mv-fav" style="color:{FAV_COLOR[fav]}" title="{TAG_LABEL[fav][2:]} với BĐS">'
        f"{FAV_GLYPH[fav] if has_value else ''}</td>"
        f'<td class="mv-imps">{_impacts(row, symbols) if has_value else ""}</td>'
        "</tr>"
    )


def block_html(title: str, rows: pd.DataFrame, ctx: BlockContext) -> str:
    head = (
        '<tr><th></th><th></th><th>Xu hướng</th><th class="r">Giá trị</th>'
        '<th class="r">Thay đổi</th><th class="c">BĐS</th><th class="c">Nhà ở · KCN</th></tr>'
    )
    body = []
    for group, part in rows.groupby("group", sort=False):
        label = html.escape(ctx.group_names.get(group, group))
        body.append(f'<tr class="mv-group"><td colspan="7">{label}</td></tr>')
        body += [
            row_html(r, ctx.sparks[r["code"]], ctx.symbols, ctx.decimals[r["code"]])
            for _, r in part.iterrows()
        ]
    return (
        f'<div class="mv-title">{html.escape(title)}</div>'
        f'<table class="mv">{COLS}{head}{"".join(body)}</table>'
    )


def dot_title(row: pd.Series) -> str:
    """Tooltip của chấm trạng thái: mức, diễn giải điểm, mô tả ngưỡng."""
    parts = [f"{STATUS_LABEL.get(row['status'], row['status'])} so với ngưỡng"]
    parts += [
        row[k]
        for k in ("threshold_detail", "threshold_note")
        if isinstance(row.get(k), str) and row[k]
    ]
    return html.escape(". ".join(parts))


def summary_strip(latest: pd.DataFrame, built: str) -> str:
    counts = latest["status"].value_counts()
    items = [
        ("red", "Đỏ"),
        ("orange", "Cam"),
        ("yellow", "Vàng"),
        ("green", "Xanh"),
        ("green_strong", "Xanh đậm"),
    ]
    items = [(k, lbl) for k, lbl in items if k in ("red", "yellow", "green") or counts.get(k, 0)]
    other = int((~latest["status"].isin([k for k, _ in items] + ["orange", "green_strong"])).sum())
    cells = [(t.STATUS_COLORS[k][1], int(counts.get(k, 0)), lbl) for k, lbl in items]
    cells.append((t.STATUS_COLORS["none"][1], other, "Chưa xếp màu"))
    html_cells = "".join(
        f'<div class="ms-item"><span class="ms-dot" style="background:{color}"></span>'
        f'<span class="ms-num">{n}</span><span class="ms-lbl">{lbl}</span></div>'
        for color, n, lbl in cells
    )
    note = f"{len(latest)} chỉ số · cập nhật {html.escape(built)}"
    return f'<div class="ms">{html_cells}<div class="ms-note">{note}</div></div>'
