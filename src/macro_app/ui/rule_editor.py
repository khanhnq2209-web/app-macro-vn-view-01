"""Bộ sửa ngưỡng một chỉ số. Chỉ trả cấu hình mới, nơi gọi tự lưu.

Không tự thay mốc người dùng đã nhập; mốc không còn hợp thì báo lỗi.
Mỗi mốc một ô số, kiểm tra tăng dần; "Gợi ý mốc" điền sẵn từ phân vị lịch sử.
"""

from __future__ import annotations

import html
import math
from itertools import pairwise

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from macro_app import fmt
from macro_app.charts import theme
from macro_app.config import Indicator
from macro_app.metrics import threshold_preview as tp
from macro_app.metrics.status import (
    DEFAULT_LABELS,
    LEVELS,
    WINDOW_METHODS,
    cuts_of,
    labels_of,
    validate_cfg,
)
from macro_app.metrics.summary import measure_text, measure_unit
from macro_app.metrics.transforms import clean, measure
from macro_app.ui import data

MEASURE_LABEL = {
    "level": "Giá trị gốc",
    "change": "Thay đổi (điểm)",
    "pct_change": "% thay đổi",
    "mean": "Trung bình trượt",
    "sum12_pct": "Tổng 12 tháng, % so cùng kỳ",
    "ytd_change": "Thay đổi từ đầu năm",
    "ytd_pct": "% thay đổi từ đầu năm",
    "pct_vs_mean": "% lệch so trung bình N năm",
}
METHOD_LABEL = {
    "absolute": "Ngưỡng cứng",
    "percentile": "Phân vị N năm",
    "zscore": "Z-score N năm",
    "median_dev": "Lệch median N năm",
    "target_band": "Lệch mục tiêu Chính phủ",
}
SIDE_LABEL = {
    "above": "Tăng là xấu",
    "below": "Tăng là tốt",
    "both": "Ở giữa là tốt",
    "middle": "Ở giữa là xấu",
}
CUT_UNIT = {
    "percentile": "phân vị",
    "zscore": "độ lệch chuẩn",
    "median_dev": "lệch so với median",
    "target_band": "lệch so với mục tiêu",
}
UNIT_LABEL = {"period": "kỳ", "day": "ngày", "year": "năm"}
FREQ_WORD = {"D": "phiên", "W": "tuần", "M": "tháng", "Q": "quý", "A": "năm"}
LOOKBACK_YEARS = [1, 3, 5, 10]
ORDER = ("green_strong", "green", "yellow", "orange", "red")


def _nice(x: float, span: float) -> float:
    """Làm tròn theo độ lớn khoảng dữ liệu, vd khoảng 3 điểm % thì bước 0,25."""
    if not span or not math.isfinite(span):
        return round(x, 2)
    step = 10 ** math.floor(math.log10(span / 4))
    for mult in (1, 2.5, 5):
        if span / (step * mult) <= 40:
            step *= mult
            break
    return round(round(x / step) * step, 6)


def suggest_cuts(
    measured: pd.Series, method: str, side: str, n_cuts: int, years: int
) -> list[float]:
    """Mốc gợi ý từ lịch sử. Ngưỡng cứng dùng phân vị 10 năm, làm tròn."""
    if method != "absolute":
        return tp.suggest_cuts(measured, method, side, n_cuts, years)
    s = clean(measured)
    w = s[s.index > s.index[-1] - pd.DateOffset(years=10)] if not s.empty else s
    if w.empty:
        return [float(i + 1) for i in range(n_cuts)]
    qs = {2: [25, 75], 3: [15, 50, 85], 4: [10, 30, 70, 90]}[n_cuts]
    raw = [float(np.percentile(w, q)) for q in qs]
    span = float(np.percentile(w, 95) - np.percentile(w, 5))
    out = sorted({_nice(x, span) for x in raw})
    while len(out) < n_cuts:  # làm tròn bị trùng thì nới đều
        out.append(out[-1] + (span / 10 or 1.0))
    return out


def starter_row(code: str, ind: Indicator, series: pd.Series) -> dict:
    """Dòng mới: ngưỡng cứng 5 mức, mốc từ phân vị 10 năm, chiều theo catalog."""
    side = {"up_good": "below", "two_way": "both"}.get(ind.direction, "above")
    return {
        "code": code,
        "method": "absolute",
        "side": side,
        "cuts": suggest_cuts(series, "absolute", side, 4, 10),
        "description": "",
    }


def _range_label(lo: float, hi: float, first: bool, last: bool) -> str:
    def f(x: float) -> str:
        return fmt.number(x, 2).rstrip("0").rstrip(",")

    if first:
        return f"dưới {f(hi)}"
    if last:
        return f"trên {f(lo)}"
    return f"{f(lo)} – {f(hi)}"


def level_strip_html(
    measured: pd.Series, cfg: dict, target: float, unit: str, scores: dict | None = None
) -> str:
    """Thanh các mức theo giá trị tăng dần, đánh dấu mức hiện tại; kèm điểm của từng mức."""
    bounds = tp.boundaries(measured, cfg, target)
    if not bounds:
        return ""
    pad = (bounds[-1] - bounds[0]) or 1.0
    zones = tp.bands(measured, cfg, target, bounds[0] - pad, bounds[-1] + pad)
    n = len(cuts_of(cfg)) + 1
    names = dict(zip(LEVELS[n], labels_of(cfg, n), strict=True))
    now = float(measured.iloc[-1])
    cells = []
    for i, (lo, hi, status) in enumerate(zones):
        bg, fg = theme.STATUS_COLORS.get(status, theme.STATUS_COLORS["none"])
        here = (i == 0 and now < hi) or (i == len(zones) - 1 and now >= lo) or lo <= now < hi
        mark = f'<div class="re-now">▲ hiện tại {fmt.number(now, 2)}{unit}</div>' if here else ""
        point = (scores or {}).get(status)
        point_txt = f" · điểm {fmt.signed(point, 0)}" if point is not None else ""
        cells.append(
            f'<div class="re-zone{" re-here" if here else ""}" style="background:{bg};color:{fg}">'
            f"<b>{html.escape(str(names.get(status, status)))}{point_txt}</b>"
            f"<span>{_range_label(lo, hi, i == 0, i == len(zones) - 1)}</span>{mark}</div>"
        )
    return f'<div class="re-strip">{"".join(cells)}</div>'


def _chart(series: pd.Series, cfg: dict, target: float, unit: str, lookback: int) -> go.Figure:
    view = series[series.index > series.index[-1] - pd.DateOffset(years=lookback)]
    bounds = tp.boundaries(series, cfg, target)
    lo, hi = float(view.min()), float(view.max())
    lo, hi = min([lo, *bounds[:1]]), max([hi, *bounds[-1:]])
    pad = (hi - lo) * 0.08 or 1.0
    y_lo, y_hi = lo - pad, hi + pad
    fig = go.Figure()
    for b_lo, b_hi, status in tp.bands(series, cfg, target, y_lo, y_hi):
        bg = theme.STATUS_COLORS.get(status, theme.STATUS_COLORS["none"])[0]
        fig.add_hrect(y0=b_lo, y1=b_hi, fillcolor=bg, opacity=0.75, line_width=0, layer="below")
    fig.add_trace(
        go.Scatter(
            x=view.index,
            y=view.to_numpy(),
            mode="lines",
            line={"color": theme.TEXT, "width": 1.6},
            hovertemplate="%{x|%d/%m/%Y}: %{y:,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[view.index[-1]],
            y=[view.iloc[-1]],
            mode="markers",
            hoverinfo="skip",
            marker={"size": 9, "color": theme.HIGHLIGHT},
        )
    )
    theme.apply_theme(fig, "", unit, height=240)
    fig.update_layout(
        showlegend=False, yaxis_range=[y_lo, y_hi], margin={"t": 8, "l": 8, "r": 8, "b": 8}
    )
    return fig


def _target(ind: Indicator, last_date) -> tuple[float, pd.Series | None]:
    if not ind.target or last_date is None:
        return np.nan, None
    t = data.target_series(ind.target, data.build_stamp())
    hit = t[t.index.year == pd.Timestamp(last_date).year]
    return (float(hit.iloc[-1]) if not hit.empty else np.nan), t


def _measure_inputs(key: str, spec: dict, ind: Indicator, disabled: bool) -> dict:
    kinds = [k for k in MEASURE_LABEL if k != "sum12_pct" or ind.frequency == "M"]
    kind_now = spec.get("kind", "level")
    kind = st.selectbox(
        "Đo gì",
        kinds,
        index=kinds.index(kind_now) if kind_now in kinds else 0,
        format_func=MEASURE_LABEL.get,
        key=f"{key}_mk",
        disabled=disabled,
    )
    if kind in ("change", "pct_change", "mean"):
        c1, c2 = st.columns(2)
        units = ["period", "day"] if kind == "mean" else list(UNIT_LABEL)
        default_unit = spec.get("unit") if spec.get("unit") in units else units[0]
        default_n = int(spec.get("n") or (1 if kind != "mean" else 3))
        n = c1.number_input(
            "Trung bình bao nhiêu" if kind == "mean" else "So với bao lâu trước",
            1,
            400,
            default_n,
            key=f"{key}_mn",
            disabled=disabled,
        )
        unit = c2.selectbox(
            "Đơn vị",
            units,
            index=units.index(default_unit),
            format_func=lambda u: (
                UNIT_LABEL[u] if u != "period" else f"kỳ ({FREQ_WORD.get(ind.frequency, 'kỳ')})"
            ),
            key=f"{key}_mu",
            disabled=disabled,
        )
        return {"kind": kind, "n": int(n), "unit": unit}
    if kind == "pct_vs_mean":
        n = st.number_input(
            "Số năm lấy trung bình",
            1,
            20,
            int(spec.get("n") or 5),
            key=f"{key}_my",
            disabled=disabled,
        )
        return {"kind": kind, "n": int(n)}
    if kind == "sum12_pct":
        ytd = st.checkbox(
            "Số gốc là lũy kế từ đầu năm",
            value=bool(spec.get("ytd", "_ytd" in ind.code)),
            key=f"{key}_ytd",
            disabled=disabled,
            help="Tách ra số từng tháng trước khi cộng 12 tháng",
        )
        return {"kind": kind, **({"ytd": True} if ytd else {})}
    return {"kind": kind}


def _method_side(key: str, cfg_now: dict, ind: Indicator, disabled: bool, cols) -> tuple:
    methods = [m for m in METHOD_LABEL if m != "target_band" or ind.target]
    method_now = cfg_now.get("method") if cfg_now.get("method") in methods else "absolute"
    with cols[0]:
        method = st.selectbox(
            "Kiểu ngưỡng",
            methods,
            index=methods.index(method_now),
            format_func=METHOD_LABEL.get,
            key=f"{key}_m",
            disabled=disabled,
        )
        years = int(cfg_now.get("window_years") or 5)
        if method in WINDOW_METHODS:
            years = int(st.number_input("N năm", 1, 20, years, key=f"{key}_y", disabled=disabled))
    sides = list(SIDE_LABEL)
    side_now = cfg_now.get("side", "both")  # cùng mặc định với status.evaluate
    side = cols[1].selectbox(
        "Chiều",
        sides,
        index=sides.index(side_now) if side_now in sides else 0,
        format_func=SIDE_LABEL.get,
        key=f"{key}_s",
        disabled=disabled,
    )
    return method, years, side


def _advanced(key: str, cfg_now: dict, n_levels: int, with_scores: bool, disabled: bool) -> tuple:
    from macro_app.metrics.scorecard import load_settings

    same_n = len(cuts_of(cfg_now) or []) + 1 == n_levels
    labels_now = labels_of(cfg_now, n_levels) if same_n else DEFAULT_LABELS[n_levels]
    default_scores = [float(x) for x in load_settings()["default_scores"][n_levels]]
    given = cfg_now.get("scores")
    scores_now = given if given and len(given) == n_levels else default_scores
    labels, scores = [], []
    title = "Nâng cao: tên mức" + (" và điểm từng mức" if with_scores else "")
    with st.expander(title):
        cols = st.columns(n_levels)
        for i, (col, status) in enumerate(zip(cols, LEVELS[n_levels], strict=True)):
            fg = theme.STATUS_COLORS[status][1]
            col.html(f'<div style="height:6px;border-radius:3px;background:{fg}"></div>')
            labels.append(
                col.text_input(
                    f"Tên mức {i + 1}",
                    labels_now[i],
                    key=f"{key}_lab{n_levels}_{i}",
                    disabled=disabled,
                )
            )
            if with_scores:
                value = col.number_input(
                    "Điểm",
                    value=float(min(2.0, max(-2.0, scores_now[i]))),
                    min_value=-2.0,
                    max_value=2.0,
                    step=0.5,
                    key=f"{key}_sc{n_levels}_{i}",
                    disabled=disabled,
                )
                scores.append(float(value))
    return labels, scores, default_scores


def _errors(cfg: dict, cuts, parse_error: str, n_levels: int, ctx: dict) -> list:
    errors = [parse_error] if parse_error else []
    if cuts is not None and len(cuts) != n_levels - 1:
        errors.append(f"{n_levels} mức cần {n_levels - 1} mốc (đang có {len(cuts)}).")
    elif cuts is not None:
        errors += validate_cfg(cfg)
    if cfg["method"] == "target_band" and np.isnan(ctx["target"]):
        errors.append("Chỉ số này chưa có mục tiêu Chính phủ cho năm của kỳ mới nhất")
    if ctx["measured"].empty:
        errors.append("Chưa có dữ liệu sau khi biến đổi")
    return errors


def _preview(key: str, cfg: dict, ctx: dict) -> None:
    measured, unit, ind, raw = ctx["measured"], ctx["unit"], ctx["ind"], ctx["raw"]
    from macro_app.metrics.scorecard import load_settings, row_scores

    n_lv = len(cfg["cuts"]) + 1
    points = dict(zip(LEVELS[n_lv], row_scores(cfg, n_lv, load_settings()), strict=True))
    st.html(level_strip_html(measured, cfg, ctx["target"], unit if unit == "%" else "", points))
    lookback = (
        st.segmented_control(
            "Xem lại",
            LOOKBACK_YEARS,
            default=5,
            format_func=lambda y: f"{y} năm",
            key=f"{key}_lookback",
        )
        or 5
    )
    st.plotly_chart(
        _chart(measured, cfg, ctx["target"], unit, lookback),
        width="stretch",
        config={"displayModeBar": False},
        key=f"{key}_chart",
    )
    hist = tp.history_scores(measured, cfg, ind.frequency, ctx["target_series"])
    since = measured.index[-1] - pd.DateOffset(years=lookback)
    shares = tp.level_shares(hist[hist.index > since], cfg)
    n = len(cfg["cuts"]) + 1
    names = dict(zip(LEVELS[n], labels_of(cfg, n), strict=True))
    share_text = " · ".join(f"{names[s]} {shares[s]:.0f}%" for s in ORDER if s in shares)
    what = measure_text(cfg.get("measure"), ind.frequency) or "giá trị gốc"
    st.caption(
        f"Đo: {what}. Dữ liệu từ {fmt.period(raw.index[0], ind.frequency)}, {len(raw)} điểm. "
        f"{lookback} năm qua: {share_text or 'chưa đủ dữ liệu'}."
    )


def _levels_and_cuts(key: str, cfg_now: dict, ctx: dict, disabled: bool) -> tuple:
    """Trả (số mức, mốc đã nhập hoặc None, lỗi). Mỗi mốc một ô số."""
    cuts_now = cuts_of(cfg_now) or []
    n_now = len(cuts_now) + 1 if len(cuts_now) + 1 in LEVELS else 5
    c4, c6 = st.columns([1, 1.4], vertical_alignment="bottom")
    levels = sorted(LEVELS)
    n_levels = c4.selectbox(
        "Số mức",
        levels,
        index=levels.index(n_now),
        key=f"{key}_l",
        disabled=disabled,
    )
    method, side, years = ctx["method"], ctx["side"], ctx["years"]
    keys = [f"{key}_cut{n_levels}_{i}" for i in range(n_levels - 1)]
    start = cuts_now if len(cuts_now) == n_levels - 1 else None
    if start is None and not ctx["measured"].empty:
        start = suggest_cuts(ctx["measured"], method, side, n_levels - 1, years)

    def fill_suggestion() -> None:
        for k, v in zip(
            keys, suggest_cuts(ctx["measured"], method, side, n_levels - 1, years), strict=True
        ):
            st.session_state[k] = float(v)

    c6.button(
        "Gợi ý mốc",
        on_click=fill_suggestion,
        key=f"{key}_suggest",
        disabled=disabled or ctx["measured"].empty,
        help="Ngưỡng cứng: phân vị 10, 30, 70, 90 của 10 năm gần nhất, làm tròn",
    )
    cut_unit = ctx["unit"] if method == "absolute" else CUT_UNIT[method]
    st.caption(f"Mốc tăng dần, đơn vị: {cut_unit}")
    cols = st.columns(len(keys))
    cuts = []
    for i, (col, k) in enumerate(zip(cols, keys, strict=True)):
        value = col.number_input(
            f"Mốc {i + 1}",
            value=float(start[i]) if start is not None else None,
            step=0.05,
            format="%.4g",
            key=k,
            disabled=disabled,
        )
        cuts.append(value)
    if any(c is None for c in cuts):
        return n_levels, None, "Còn ô mốc trống"
    if any(b <= a for a, b in pairwise(cuts)):
        return n_levels, None, "Mốc phải tăng dần (ô sau lớn hơn ô trước)"
    return n_levels, [float(c) for c in cuts], ""


def edit(
    code: str, cfg_now: dict, *, key: str, with_scores: bool = False, disabled: bool = False
) -> dict | None:
    """Trả cấu hình mới, None nếu đang lỗi. Không lưu."""
    ind = data.catalog_map()[code]
    raw = data.series(code).dropna()
    if raw.empty:
        st.info("Chỉ số chưa có dữ liệu.")
        return None
    target_value, target_series = _target(ind, raw.index[-1])

    c1, c2, c3 = st.columns(3)
    with c1:
        spec = _measure_inputs(key, cfg_now.get("measure") or {}, ind, disabled)
    method, years, side = _method_side(key, cfg_now, ind, disabled, (c2, c3))
    measured = measure(raw, ind.frequency, spec)
    ctx = {
        "measured": measured,
        "unit": measure_unit(spec, ind.unit),
        "ind": ind,
        "raw": raw,
        "target": target_value,
        "target_series": target_series,
        "method": method,
        "side": side,
        "years": years,
    }
    n_levels, cuts, parse_error = _levels_and_cuts(key, cfg_now, ctx, disabled)
    desc = st.text_area(
        "Căn cứ / mô tả",
        cfg_now.get("description", ""),
        key=f"{key}_d",
        height=68,
        disabled=disabled,
        placeholder="Lý do chọn mốc, nguồn tham chiếu",
    )
    labels, scores, default_scores = _advanced(key, cfg_now, n_levels, with_scores, disabled)

    cfg = {"method": method, "side": side, "cuts": cuts or [], "description": desc.strip()}
    if spec["kind"] != "level":
        cfg["measure"] = spec
    if method in WINDOW_METHODS:
        cfg["window_years"] = years
    if labels != list(DEFAULT_LABELS[n_levels]):
        cfg["labels"] = labels
    if with_scores and scores != default_scores:
        cfg["scores"] = scores

    errors = _errors(cfg, cuts, parse_error, n_levels, ctx)
    if errors:
        st.error(" · ".join(errors))
        return None
    _preview(key, cfg, ctx)
    return cfg
