"""Hiển thị scorecard: gauge, 3 thẻ đầu trang, bảng theo nhóm, biểu đồ điểm theo tháng.

Mọi chuỗi người dùng nhập (tên nhóm, tên bộ, mô tả) đều qua html.escape: ai có mật khẩu cũng
sửa được cấu hình, còn người xem là bất kỳ ai.
"""

from __future__ import annotations

import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from macro_app import fmt
from macro_app.charts import theme as t
from macro_app.metrics.scorecard import rating
from macro_app.metrics.status import LEVELS, cuts_of, labels_of

RATING_COLOR = {
    "Rất thuận lợi": "green_strong",
    "Thuận lợi": "green",
    "Trung tính": "yellow",
    "Bất lợi": "orange",
    "Rất bất lợi": "red",
}
SCORE_STATUS = {2: "green_strong", 1: "green", 0: "yellow", -1: "orange", -2: "red"}
SCORE_NAME = {2: "Rất tốt", 1: "Tốt", 0: "Trung tính", -1: "Xấu", -2: "Rất xấu"}
SCORE_SYMBOL = {2: "⇈", 1: "↑", 0: "●", -1: "↓", -2: "⇊"}
GAUGE_RANGE = (-1.0, 1.2)  # phóng to vùng có các mốc xếp hạng; điểm ngoài khoảng ghim ở hai đầu
GOOD, BAD, FLAT = "#1E7B34", "#B3261E", "#5F6B73"
REF_KIND = {"target": "Mục tiêu", "market": "Kỳ vọng"}  # forward.ForwardPoint.kind
E = html.escape


def _chip(text: str, status: str, title: str = "", extra: str = "") -> str:
    bg, fg = t.STATUS_COLORS.get(status, t.STATUS_COLORS["none"])
    tip = f' title="{E(title)}"' if title else ""
    return (
        f'<span class="sc3-chip {extra}" style="background:{bg};color:{fg}"{tip}>{E(text)}</span>'
    )


def rating_chip(label: str) -> str:
    return _chip(label, RATING_COLOR.get(label, "none"))


def _bucket(score) -> int | None:
    if score is None or pd.isna(score):
        return None
    return int(max(-2, min(2, np.floor(float(score) + 0.5))))  # 0,5 làm tròn lên


def level_chip(score) -> str:
    b = _bucket(score)
    if b is None:
        return _chip("Không có số", "none", extra="dash")
    return _chip(f"{SCORE_SYMBOL[b]} {SCORE_NAME[b]}", SCORE_STATUS[b])


# --- Thẻ 1: gauge + điểm ---


R_OUT, R_IN = 1.0, 0.74  # bán kính ngoài / trong của cung màu
GAP = 0.012  # khe giữa các dải (radian)


def _angle(v: float) -> float:
    lo, hi = GAUGE_RANGE
    return np.pi * (1 - (np.clip(v, lo, hi) - lo) / (hi - lo))


def _xy(r: float, a: float) -> tuple[float, float]:
    return r * np.cos(a), r * np.sin(a)


def _path(points: list[tuple[float, float]]) -> str:
    return "M " + " L ".join(f"{x:.4f},{y:.4f}" for x, y in points) + " Z"


def _sector(a0: float, a1: float) -> str:
    """Hình quạt vành khăn từ góc a0 tới a1 (a0 > a1, quay theo chiều kim đồng hồ)."""
    arc = np.linspace(a0, a1, 40)
    outer = [_xy(R_OUT, a) for a in arc]
    inner = [_xy(R_IN, a) for a in arc[::-1]]
    return _path(outer + inner)


def _needle(a: float) -> str:
    """Kim thuôn: mũi nhọn ở cung trong, đuôi ngắn sau trục."""
    tip = _xy(R_IN - 0.04, a)
    tail = _xy(-0.13, a)
    side = a + np.pi / 2
    left, right = _xy(0.045, side), _xy(-0.045, side)
    return _path([tip, left, tail, right])


def gauge_figure(score: float, bands: list[dict]) -> go.Figure:
    """Gauge bán nguyệt: 5 dải xếp hạng, kim chỉ điểm, nhãn mốc ngoài cung."""
    lo, hi = GAUGE_RANGE
    tops = [hi, *[b["min"] for b in bands[:-1]]]
    fig = go.Figure(
        go.Scatter(
            x=[-1.3, 1.3], y=[-0.2, 1.2], mode="markers", marker={"opacity": 0}, hoverinfo="skip"
        )
    )
    for band, top in zip(bands, tops, strict=True):
        start, end = max(band["min"], lo), min(top, hi)
        if end <= start:
            continue
        a0, a1 = _angle(start), _angle(end)
        a0 -= GAP / 2 if start > lo else 0
        a1 += GAP / 2 if end < hi else 0
        fig.add_shape(
            type="path",
            path=_sector(a0, a1),
            fillcolor=t.RATING_SCALE[band["label"]],
            line_width=0,
            layer="below",
        )
    labels = [(b["min"], fmt.number(b["min"], 2)) for b in bands if lo < b["min"] < hi]
    labels += [(lo, "≤ −1"), (hi, "≥ 1,2")]
    for v, text in labels:
        x, y = _xy(R_OUT + 0.13, _angle(v))
        fig.add_annotation(
            x=x, y=max(y, -0.07), text=text, showarrow=False, font={"size": 11, "color": t.MUTED}
        )
    if pd.notna(score):
        a = _angle(score)
        fig.add_shape(type="path", path=_needle(a), fillcolor=t.HEADING, line_width=0)
    fig.add_shape(
        type="circle", x0=-0.085, y0=-0.085, x1=0.085, y1=0.085, fillcolor=t.HEADING, line_width=0
    )
    fig.add_shape(
        type="circle", x0=-0.035, y0=-0.035, x1=0.035, y1=0.035, fillcolor="#FFFFFF", line_width=0
    )
    axis = {"visible": False, "fixedrange": True}
    fig.update_layout(
        height=190,
        margin={"t": 6, "b": 0, "l": 6, "r": 6},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis={**axis, "range": [-1.32, 1.32]},
        yaxis={**axis, "range": [-0.2, 1.22], "scaleanchor": "x"},
        font={"family": t.FONT, "color": t.TEXT},
    )
    return fig


def score_html(total: dict, cmp: dict, cmp_label: str) -> str:
    score = total["score"]
    if pd.isna(score):
        last = total.get("last_score")
        when = total.get("last_date")
        note = (
            f"Chưa đủ dữ liệu tháng này. Gần nhất đủ dữ liệu: {pd.Timestamp(when):%m/%Y} · "
            f"{fmt.signed(last, 2)} ({E(str(total.get('last_rating', '')))})"
            if pd.notna(last)
            else "Chưa đủ dữ liệu để chấm."
        )
        return f'<div class="sc3-score"><span class="sc3-num">—</span></div><div class="sc3-sub">{note}</div>'
    prev = cmp.get("total", np.nan)
    when = pd.Timestamp(cmp["date"]).strftime("T%m/%Y") if cmp.get("date") is not None else ""
    delta = (
        f"{fmt.signed(score - prev, 2)} so với {E(cmp_label)} ({when}: {fmt.signed(prev, 2)})"
        if pd.notna(prev)
        else f"chưa có điểm {E(cmp_label)} để so"
    )
    return (
        f'<div class="sc3-score"><span class="sc3-num">{fmt.signed(score, 2)}</span>'
        f"{rating_chip(total['rating'])}</div>"
        f'<div class="sc3-sub">{delta} · mỗi chỉ số chấm từ −2 đến +2</div>'
    )


def meaning_html(meaning: str) -> str:
    """Một dòng dưới điểm: bất lợi / thuận lợi nghĩa là chỉ tiêu sẽ tăng hay giảm, trong bao lâu."""
    return f'<div class="sc3-meaning">{E(meaning)}</div>' if meaning else ""


def card_head_html(name: str, saved: dict | None) -> str:
    if saved:
        at = str(saved.get("saved_at", ""))[:10]
        at = f"{at[8:10]}/{at[5:7]}/{at[:4]}" if len(at) == 10 else at
        badge = (
            f'<span class="sc3-badge" title="Phiên bản {saved.get("version")}">'
            f"Cập nhật {E(at)} bởi {E(str(saved.get('saved_by', '')))}</span>"
        )
    else:
        badge = '<span class="sc3-badge" title="Chưa ai sửa trên app">Bản gốc trong repo</span>'
    return f'<div class="sc3-cardhead"><b>{E(name)}</b>{badge}</div>'


# --- Thẻ 2: vì sao ---


def why_html(pillars: list[dict], cmp: dict, cmp_label: str, score: float) -> str:
    ps = [p for p in pillars if pd.notna(p.get("contribution"))]
    if not ps:
        return (
            '<div class="sc3-title">Vì sao điểm thế này</div><div class="sc3-sub">Chưa có số.</div>'
        )
    top = max(abs(p["contribution"]) for p in ps) or 1.0
    bars = []
    for p in sorted(ps, key=lambda x: x["contribution"]):
        c = p["contribution"]
        width = abs(c) / top * 50
        side = f"left:50%;width:{width:.1f}%" if c >= 0 else f"right:50%;width:{width:.1f}%"
        color = t.STATUS_COLORS["green"][1] if c >= 0 else t.STATUS_COLORS["orange"][1]
        bars.append(
            f'<span class="sc3-dn">{E(p["pillar"])}</span>'
            f'<span class="sc3-track"><i style="{side};background:{color}"></i></span>'
            f"<b>{fmt.signed(c, 2)}</b>"
        )
    prev = cmp.get("pillars") or {}
    moves = [  # nhóm không có ở kỳ trước thì không tính là đổi
        (p["pillar"], p["contribution"] - prev[p["pillar"]])
        for p in ps
        if p["pillar"] in prev and abs(p["contribution"] - prev[p["pillar"]]) > 0.005
    ]
    moved = (
        " · ".join(f"{E(n)} {fmt.signed(d, 2)}" for n, d in moves)
        if prev
        else f"chưa có số {E(cmp_label)}"
    )
    return (
        '<div class="sc3-title">Vì sao điểm thế này</div>'
        f'<div class="sc3-sub">Đóng góp từng nhóm, cộng lại = {fmt.signed(score, 2) if pd.notna(score) else "—"}</div>'
        f'<div class="sc3-drv">{"".join(bars)}</div>'
        f'<div class="sc3-small"><b>Đổi so {E(cmp_label)}:</b> {moved or "không đổi"}</div>'
    )


# --- Thẻ 3: độ tin cậy ---


def trust_html(
    total: dict, table: pd.DataFrame, names: dict, latest: pd.DataFrame, bands: list[dict]
) -> str:
    cov = total.get("coverage", 0.0)
    scored = table[~table["info"].astype(bool)] if not table.empty else table
    stale = scored[scored["stale"].astype(bool)] if not scored.empty else scored
    lat = latest.set_index("code") if not latest.empty else pd.DataFrame()
    chips = []
    for _, r in stale.iterrows():
        last = SCORE_NAME.get(_bucket(r.get("last_score")), "chưa có số")
        when = ""
        if r["code"] in lat.index:
            when = fmt.period(lat.loc[r["code"], "period"], lat.loc[r["code"], "frequency"])
        chips.append(
            _chip(
                f"{names.get(r['code'], r['code'])} · {last}",
                "none",
                title=f"Số cũ, kỳ cuối {when}; mức cuối đã biết: {last}",
            )
        )
    head = f"Độ phủ trọng số <b>{fmt.number(cov * 100, 0)}%</b>" + (
        f" · {len(stale)} chỉ số số cũ không tính ({fmt.number(stale['weight'].sum() * 100, 1)}%)"
        if len(stale)
        else " · mọi chỉ số đều có số mới"
    )
    sens = total.get("sensitivity") or {}
    alert = ""
    if sens:
        flip = rating(sens["worst"], bands) != rating(sens["best"], bands)
        alert = (
            '<div class="sc3-alert"><b>Nếu số cũ quay lại:</b> giữ mức cuối đã biết → '
            f"<b>{fmt.signed(sens['keep'], 2)}</b> ({E(rating(sens['keep'], bands))}). "
            f"Biên độ <b>{fmt.signed(sens['worst'], 2)}</b> … <b>{fmt.signed(sens['best'], 2)}</b>"
            + (" · <b>có thể đổi xếp hạng</b>" if flip else "")
            + "</div>"
        )
    return (
        '<div class="sc3-title">Độ tin cậy</div>'
        f'<div class="sc3-small">{head}</div>'
        f'<div class="sc3-cov"><i style="width:{min(cov, 1) * 100:.0f}%"></i></div>'
        f'<div class="sc3-chips">{"".join(chips)}</div>{alert}'
    )


# --- Bảng ---


def next_worse(row: dict, measured: float, status: str, unit: str) -> str:
    """'cách mức Xấu: 0,35 điểm %' cho ngưỡng cứng một phía."""
    cuts = cuts_of(row) or []
    n = len(cuts) + 1
    usable = (
        row.get("method") == "absolute"
        and row.get("side") in ("above", "below")
        and n in LEVELS
        and status in LEVELS[n][:-1]  # mức xấu nhất thì không còn mức xấu hơn
        and pd.notna(measured)
    )
    if not usable:
        return ""
    i = LEVELS[n].index(status)
    edges = sorted(cuts)
    # Cùng quy ước với status._level: giá trị đúng bằng mốc thuộc mức tốt hơn, nên mốc đang
    # đứng đúng trên nó cũng là ranh giới sang mức xấu hơn (khoảng cách 0).
    if row["side"] == "above":
        edge = next((c for c in edges if c >= measured), None)
    else:
        edge = next((c for c in reversed(edges) if c <= measured), None)
    if edge is None:
        return ""
    unit_txt = "điểm %" if unit == "%" else unit
    return f"cách mức {labels_of(row, n)[i + 1]}: {fmt.number(abs(edge - measured), 2)} {unit_txt}"


def _value_cell(rec: pd.Series, decimals: int) -> str:
    what = rec.get("measure_text") or "giá trị gốc"
    if rec.get("measure_text"):  # số đã biến đổi (% thay đổi, trung bình...): ít nhất 1 số lẻ
        decimals = max(decimals, 1)
    value, unit = rec.get("measured"), rec.get("measured_unit") or ""
    if pd.isna(value):
        return '<td class="r" title="Chưa có số hoặc số nhà cung cấp chỉ hiện nội bộ"><span class="mv-empty">—</span></td>'
    unit_html = "%" if unit == "%" else f'<span class="mv-unit">{E(unit)}</span>'
    return (
        f'<td class="r" title="Cách đo: {E(what)}">'
        f'<span class="sc3-val">{fmt.number(value, decimals)}</span>{unit_html}</td>'
    )


def _level_cell(rec: pd.Series, row: dict, lat: pd.Series) -> str:
    if rec.get("show_level") is False:
        return '<td><span class="mv-empty">–</span></td>'
    if bool(rec.get("info")):
        return f"<td>{_chip('Tham khảo', 'none', 'Chỉ tham khảo, không vào điểm')}</td>"
    if bool(rec.get("stale")):
        last = rec.get("label") or "chưa chấm"
        when = fmt.period(lat["period"], lat["frequency"]) if lat is not None else ""
        tip = f"Số cũ (kỳ cuối {when}), không tính điểm. Mức cuối đã biết: {last}"
        return f"<td>{_chip('Không tính · số cũ', 'none', tip, 'dash')}</td>"
    status = rec["status"] if rec["status"] in SCORE_STATUS.values() else "none"
    tip = next_worse(row, rec.get("measured"), rec["status"], rec.get("measured_unit") or "")
    return f"<td>{_chip(rec.get('label') or 'chưa chấm', status, tip)}</td>"


def _cmp_cell(rec: pd.Series, prev_rows: dict) -> str:
    prev = prev_rows.get(rec["code"])
    if bool(rec.get("info")) or pd.isna(rec.get("score")) or prev is None or pd.isna(prev):
        return "<td></td>"
    diff = float(rec["score"]) - float(prev)
    tip = f'title="từ {E(SCORE_NAME.get(_bucket(prev), ""))}"'
    if abs(diff) < 1e-9:
        return f'<td class="sc3-cmp" {tip}><span class="mv-empty">=</span></td>'
    color, arrow = (GOOD, "▲") if diff > 0 else (BAD, "▼")
    return f'<td class="sc3-cmp" {tip} style="color:{color}">{arrow} {fmt.signed(diff, 0)} bậc</td>'


def _ref_cell(rec: pd.Series, lat: pd.Series | None, decimals: int) -> str:
    value = rec.get("fwd_value")
    if value is None or pd.isna(value) or lat is None:
        return '<td><span class="mv-empty">—</span></td>'
    unit = lat["unit"]
    shown = fmt.number(value, 0 if float(value).is_integer() else decimals)
    shown += "%" if unit == "%" else f" {E(unit)}"
    kind = REF_KIND.get(str(rec.get("fwd_kind")), "Tham khảo")
    if kind == "Mục tiêu" and unit not in ("%", "điểm %"):
        kind = "Kế hoạch"  # số tuyệt đối (vốn đầu tư...) là kế hoạch năm
    tip = f"{rec.get('fwd_source', '')} · {rec.get('fwd_when', '')}: {rec.get('fwd_text', '')}"
    return f'<td title="{E(tip)}">{shown} <span class="sc3-kind">· {kind}</span></td>'


def table_html(  # noqa: PLR0913
    table: pd.DataFrame,
    latest: pd.DataFrame,
    catalog: dict,
    card: dict,
    total: dict,
    *,
    cmp: dict,
    cmp_label: str,
    sparks: dict,
    show_weights: bool,
) -> str:
    lat = latest.set_index("code")
    rows_cfg = {r["code"]: r for r in card["rows"]}
    prev_rows, prev_pillars = cmp.get("rows") or {}, cmp.get("pillars") or {}
    w_head = (
        '<th class="r m-hide">Trọng số thực dùng</th><th class="r m-hide">Đóng góp</th>'
        if show_weights
        else ""
    )
    w_cols = '<col style="width:92px"><col style="width:80px">' if show_weights else ""
    head = (
        '<colgroup><col><col class="m-hide" style="width:96px"><col style="width:120px">'
        f'<col style="width:150px"><col style="width:120px"><col style="width:190px">{w_cols}</colgroup>'
        '<tr><th>Chỉ số</th><th class="m-hide">Diễn biến 3 năm</th><th class="r">Giá trị dùng chấm</th>'
        f"<th>Mức</th><th>So {E(cmp_label)}</th><th>Thông tin tham khảo</th>{w_head}</tr>"
    )
    body = []
    for p in total.get("pillars", []):
        name = p["pillar"]
        part = table[table["pillar"] == name]
        delta = ""
        if name in prev_pillars and pd.notna(p["contribution"]):
            d = p["contribution"] - prev_pillars[name]
            delta = (
                '<span class="mv-empty">= giữ mức</span>'
                if abs(d) < 0.0005
                else f'<span style="color:{GOOD if d > 0 else BAD}">{"▲" if d > 0 else "▼"} '
                f"{fmt.signed(d, 3)} đóng góp</span>"
            )
        w_cells = (
            f'<td class="r m-hide" title="Trọng số cấu hình của nhóm">{fmt.number(p["weight"] * 100, 0)}%</td>'
            f'<td class="r m-hide"><b>{fmt.signed(p["contribution"], 3) if pd.notna(p["contribution"]) else "—"}</b></td>'
            if show_weights
            else ""
        )
        body.append(
            f'<tr class="sc3-group"><td colspan="3"><b>{E(name)}</b>'
            f'<span class="sc3-gnote">{p["n_scored"]}/{p["n_all"]} chỉ số tính điểm</span></td>'
            f"<td>{level_chip(p['level'])}</td><td>{delta}</td><td></td>{w_cells}</tr>"
        )
        for _, rec in part.iterrows():
            code = rec["code"]
            row_lat = lat.loc[code] if code in lat.index else None
            ind = catalog[code]
            name_txt = E(ind.name)
            when = (
                fmt.period(row_lat["period"], row_lat["frequency"]) if row_lat is not None else ""
            )
            w_cells = ""
            if show_weights:
                if bool(rec.get("info")):
                    w_cells = '<td class="r m-hide"><span class="mv-empty">—</span></td><td class="r m-hide"></td>'
                else:
                    contrib = rec.get("contribution")
                    w_cells = (
                        f'<td class="r m-hide" title="Cấu hình {fmt.number(rec["weight"] * 100, 1)}%">'
                        f"{fmt.number(rec.get('weight_used', 0) * 100, 1)}%</td>"
                        f'<td class="r m-hide">{fmt.signed(contrib, 3) if pd.notna(contrib) else "—"}</td>'
                    )
            body.append(
                f'<tr class="{"sc3-ex" if not bool(rec.get("info")) and pd.isna(rec.get("score")) else ""}">'
                f'<td class="mv-name"><a href="detail?code={E(code)}" target="_self" title="{name_txt}">{name_txt}</a>'
                f'<div class="mv-meta">Cập nhật {when}</div></td>'
                f'<td class="mv-spark m-hide">{sparks.get(code, "")}</td>'
                f"{_value_cell(rec, ind.decimals)}"
                f"{_level_cell(rec, rows_cfg.get(code, {}), row_lat)}"
                f"{_cmp_cell(rec, prev_rows)}"
                f"{_ref_cell(rec, row_lat, ind.decimals)}"
                f"{w_cells}</tr>"
            )
    score = total.get("score")
    note = (
        f' <span class="sc3-gnote">· trọng số thực dùng = cấu hình ÷ độ phủ {fmt.number(total.get("coverage", 0) * 100, 1)}%</span>'
        if show_weights
        else ""
    )
    sum_cell = ""
    if show_weights:
        contrib = table["contribution"].sum(min_count=1) if "contribution" in table else np.nan
        sum_cell = f'<td class="r m-hide"></td><td class="r m-hide"><b>{fmt.signed(contrib, 3) if pd.notna(contrib) else "—"}</b></td>'
    total_row = (
        f'<tr class="sc3-total"><td colspan="6">Tổng đóng góp = điểm tổng '
        f"{fmt.signed(score, 3) if pd.notna(score) else '—'}{note}</td>{sum_cell}</tr>"
    )
    return (
        f'<div class="sc-wrap"><table class="mv sc3">{head}{"".join(body)}{total_row}</table></div>'
    )


# --- Lịch sử ---


def history_chart(hist: pd.DataFrame, bands: list[dict]) -> go.Figure:
    fig = go.Figure()
    scores = hist["score"].dropna()
    lo = max(-2.2, min(float(scores.min()) if len(scores) else -1.0, -0.6) - 0.2)
    hi = min(2.2, max(float(scores.max()) if len(scores) else 1.0, 1.1) + 0.2)
    tops = [hi, *[b["min"] for b in bands[:-1]]]
    for top, band in zip(tops, bands, strict=True):
        y0, y1 = max(band["min"], lo), min(top, hi)
        if y1 <= y0:
            continue
        bg = t.STATUS_COLORS.get(RATING_COLOR.get(band["label"], "none"))[0]
        fig.add_hrect(y0=y0, y1=y1, fillcolor=bg, opacity=0.6, line_width=0, layer="below")
        rng = (
            f"≥ {fmt.number(band['min'], 2)}"
            if top >= hi
            else (
                f"< {fmt.number(top, 2)}"
                if band["min"] <= lo
                else f"{fmt.number(band['min'], 2)} – {fmt.number(top, 2)}"
            )
        )
        fig.add_annotation(
            x=1.0,
            xref="paper",
            xanchor="left",
            y=(y0 + y1) / 2,
            text=f"{band['label']} <span style='color:{t.MUTED}'>{rng}</span>",
            showarrow=False,
            font={"size": 11, "color": t.TEXT},
        )
    cov = hist["coverage"] if "coverage" in hist else pd.Series(np.nan, index=hist.index)
    fig.add_trace(
        go.Scatter(
            x=hist["date"],
            y=hist["score"],
            customdata=(cov * 100).to_numpy(),
            mode="lines",
            name="Điểm",
            line={"color": t.HEADING, "width": 2},
            hovertemplate="%{x|%m/%Y}: %{y:+.2f} · độ phủ %{customdata:.0f}%<extra></extra>",
        )
    )
    last = hist.dropna(subset=["score"]).tail(1)
    if not last.empty:
        fig.add_trace(
            go.Scatter(
                x=last["date"],
                y=last["score"],
                mode="markers",
                hoverinfo="skip",
                marker={"size": 9, "color": t.HIGHLIGHT},
            )
        )
    t.apply_theme(fig, "", "điểm", height=300)
    fig.update_layout(
        showlegend=False, yaxis_range=[lo, hi], margin={"t": 10, "l": 8, "r": 150, "b": 8}
    )
    return fig


# --- Giữ cho trang Kế hoạch & dự báo, Chi tiết ---


def implications_html(items: list[dict]) -> str:
    """Khối "AI comment": mỗi chỉ số bất lợi / thuận lợi một dòng, bất lợi trước."""
    if not items:
        return (
            '<div class="sc3-imp"><div class="sc3-imp-head"><span class="sc3-ai">✦ AI comment</span>'
            '</div><div class="sc3-imp-sub">Các chỉ số đều ở mức trung tính.</div></div>'
        )
    icon = {"bad": ("▼", t.STATUS_COLORS["orange"][1]), "good": ("▲", t.STATUS_COLORS["green"][1])}
    lines = []
    for x in items:
        mark, color = icon.get(x["tone"], ("●", t.MUTED))
        label = (
            f" · {E(x['label'])}"
            if x["label"] and x["code"] not in ("fed_upper", "fed_lower", "effr")
            else ""
        )
        lines.append(
            f'<li><span class="sc3-imp-mark" style="color:{color}">{mark}</span>'
            f"<b>{E(x['name'])}</b><span class='sc3-imp-lbl'>{label}</span>: {E(x['text'])}</li>"
        )
    return (
        '<div class="sc3-imp"><div class="sc3-imp-head"><span class="sc3-ai">✦ AI comment</span>'
        '<span class="sc3-imp-sub">tác động lên Việt Nam</span></div>'
        f"<ul>{''.join(lines)}</ul></div>"
    )


def fed_path_html(path: pd.DataFrame, current_upper: float, n: int = 8) -> str:
    """Bảng kỳ họp FOMC: biên trên kỳ vọng, chênh so với hiện tại, khoảng xác suất cao nhất."""
    from macro_app.metrics import implications as im

    if path.empty:
        return ""
    outlook = im.fed_summary(im.fed_outlook(path, current_upper))
    ahead = path[path["meeting_date"] > path["asof"].max()].head(n)
    rows = []
    for _, r in ahead.iterrows():
        diff = (r["exp_upper"] - current_upper) * 100 if pd.notna(current_upper) else float("nan")
        diff_txt = "—" if pd.isna(diff) else f"{diff:+.0f} bps"
        rows.append(
            f"<tr><td>{r['meeting_date']:%d/%m/%Y}</td>"
            f'<td class="r">{fmt.number(r["exp_upper"], 2)}%</td><td class="r">{diff_txt}</td>'
            f"<td>{r['top_range'].replace('.', ',')} · {r['top_prob'] * 100:.0f}%</td></tr>"
        )
    asof = ahead["asof"].max() if not ahead.empty else path["asof"].max()
    src = "CME FedWatch" if "CME" in str(path["source"].iloc[0]) else "FedWatch tự tính từ ZQ"
    return (
        (f'<div class="sc-fed-sum">{E(outlook)}.</div>' if outlook else "")
        + '<table class="mv mi sc-fed"><tr><th>Kỳ họp</th><th class="r">Biên trên kỳ vọng</th>'
        '<th class="r">So hiện tại</th><th>Khả năng cao nhất</th></tr>'
        f"{''.join(rows)}</table>"
        f"<p class='mc-note'>{src}, ngày {asof:%d/%m/%Y}. Biên trên kỳ vọng = bình quân "
        "theo xác suất. Là kỳ vọng thị trường, không phải dự báo của Fed.</p>"
    )


def forecast_map_html(df: pd.DataFrame) -> str:
    """Bảng thực tế so với kế hoạch / dự báo (chỉ số liệu, không tô màu tốt/xấu)."""
    from macro_app.ui import monitor

    head = (
        '<colgroup><col><col style="width:110px"><col style="width:150px"><col style="width:130px">'
        '<col style="width:34%"></colgroup>'
        '<tr><th>Chỉ số thực tế</th><th class="r">Thực tế</th><th class="r">Kế hoạch / Dự báo</th>'
        '<th>Chênh</th><th class="m-hide">Ghi chú</th></tr>'
    )

    def text(x) -> str:  # ô trống (None/NaN) hiện trống, không hiện chữ "None"
        return "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x)

    body = []
    for _, r in df.iterrows():
        unit = r["unit"]
        actual = monitor._value(r["actual"], unit, 2 if unit in ("%", "điểm %") else 0)
        when_actual = (
            fmt.period(r["actual_date"], r["frequency"]) if pd.notna(r["actual_date"]) else ""
        )
        if r["error"]:
            plan = f'<span class="sc-warn">{E(r["error"])}</span>'
            change = ""
        elif pd.isna(r["plan"]):
            plan, change = '<span class="mi-none">chưa có số</span>', ""
        else:
            when = str(r["plan_when"]).replace("mục tiêu ", "").replace("kỳ ", "")
            plan = (
                f'{monitor._value(r["plan"], unit, 2 if unit in ("%", "điểm %") else 0)}<div class="mv-meta">'
                f"{E(' · '.join(p for p in (text(r['label']), when) if p))}</div>"
            )
            # Trang chỉ xem số: chênh lệch không tô màu tốt/xấu (chấm điểm chỉ ở Scorecard)
            change = _change_html(
                r["change"], unit, "", r["actual"], plan=r["plan"], kind=r["kind"]
            )
        tip = E(f"{text(r['plan_source'])}: {r['others']}") if text(r["others"]) else ""
        body.append(
            f'<tr><td class="mv-name"><a href="detail?code={r["code"]}" target="_self">'
            f'{E(r["name"])}</a><div class="mv-meta m-hide">{E(str(r["code"]))}</div></td>'
            f'<td class="mv-val">{actual}<div class="mv-meta">{when_actual}</div></td>'
            f'<td class="mv-val" title="{tip}">{plan}</td>'
            f'<td class="sc-trend">{change}</td>'
            f'<td class="mv-meta m-hide">{E(text(r["note"]))}</td></tr>'
        )
    return f'<div class="sc-wrap"><table class="mv mi">{head}{"".join(body)}</table></div>'


def _change_html(  # noqa: PLR0913
    change: float, unit: str, direction: str, actual: float, *, plan: float, kind: str
) -> str:
    if change is None or pd.isna(change):
        return ""
    if kind in ("target", "manual") and unit not in ("%", "điểm %") and actual and plan:
        return f'<span style="color:{FLAT}">đạt {fmt.number(actual / plan * 100, 1)}% KH</span>'
    good = {"up_good": 1, "up_bad": -1}.get(direction, 0) * (
        1 if change > 0 else -1 if change < 0 else 0
    )
    color = GOOD if good > 0 else BAD if good < 0 else FLAT
    arrow = "▲" if change > 0 else "▼" if change < 0 else "▶"
    if unit in ("%", "điểm %"):
        txt = f"{fmt.signed(change, 2)} điểm %"
    else:
        txt = f"{fmt.signed(change / actual * 100, 1)}%" if actual else ""
    return f'<span style="color:{color}"><span class="sc-arrow">{arrow}</span>{txt}</span>'
