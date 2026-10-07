"""Hiển thị scorecard: đầu trang, bảng theo trụ cột, biểu đồ điểm theo tháng."""

from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go

from macro_app import fmt
from macro_app.charts import theme as t
from macro_app.ui import monitor

RATING_COLOR = {
    "Rất thuận lợi": "green_strong",
    "Thuận lợi": "green",
    "Trung tính": "yellow",
    "Bất lợi": "orange",
    "Rất bất lợi": "red",
}


def rating_chip(label: str) -> str:
    bg, fg = t.STATUS_COLORS.get(RATING_COLOR.get(label, "none"), t.STATUS_COLORS["none"])
    return f'<span class="sc-chip" style="background:{bg};color:{fg}">{html.escape(label)}</span>'


def header_html(total: pd.Series, description: str, names: dict | None = None) -> str:
    score = total["score"]
    prev = total.get("prev_score")
    delta = ""
    if pd.notna(score) and pd.notna(prev):
        delta = f'<span class="sc-delta">{fmt.signed(score - prev, 2)} so tháng trước</span>'
    shown = fmt.signed(score, 2) if pd.notna(score) else "—"
    stale = int(total.get("n_stale") or 0)
    note = f" · {stale} chỉ số số cũ, không tính" if stale else ""
    bad = [c for c in str(total.get("stale_bad") or "").split(",") if c]
    warn = ""
    if bad:
        bad_names = ", ".join((names or {}).get(c, c) for c in bad)
        warn = (
            '<div class="sc-warn">Điểm có thể lạc quan: chưa tính '
            f"{html.escape(bad_names)} (số cũ, lần cuối ở mức xấu).</div>"
        )
    if pd.isna(score) and pd.notna(total.get("last_score")):
        delta = (
            f'<span class="sc-delta">Gần nhất đủ dữ liệu: {pd.Timestamp(total["last_date"]):%m/%Y} · '
            f"{fmt.signed(total['last_score'], 2)} ({html.escape(total['last_rating'])})</span>"
        )
    return (
        '<div class="sc-head">'
        f'<div><div class="sc-name">{html.escape(total["name"])}</div>'
        f'<div class="sc-desc">{html.escape(description)}</div></div>'
        f'<div class="sc-score"><span class="sc-num">{shown}</span>{rating_chip(total["rating"])}'
        f"{delta}<div class='sc-cov'>độ phủ dữ liệu {fmt.number(total['coverage'] * 100, 0)}%{note} · thang −2 đến +2</div></div>"
        "</div>"
        f"{warn}"
    )


SCORE_SYMBOL = {2: "⇈", 1: "↑", 0: "●", -1: "↓", -2: "⇊"}
SCORE_STATUS = {2: "green_strong", 1: "green", 0: "yellow", -1: "orange", -2: "red"}


def _bucket(score: float) -> int | None:
    """Làm tròn điểm về bậc gần nhất trong −2..+2."""
    if score is None or pd.isna(score):
        return None
    return int(max(-2, min(2, round(float(score)))))


def _box(score: float, title: str = "", status: str | None = None, *, muted: bool = False) -> str:
    b = _bucket(score)
    if b is None:
        return (
            f'<td class="mi-cell" title="{html.escape(title)}"><span class="mi-none">–</span></td>'
        )
    bg, fg = t.STATUS_COLORS.get(status or SCORE_STATUS[b], t.STATUS_COLORS["none"])
    style = f"background:{bg};color:{fg}" + (";opacity:.45" if muted else "")
    return (
        f'<td class="mi-cell" title="{html.escape(title)}">'
        f'<span style="{style}">{SCORE_SYMBOL[b]}</span></td>'
    )


def _counts(scores: pd.Series) -> str:
    s = scores.dropna().map(_bucket)
    return " ".join(
        f"{(s == k).sum()}{SCORE_SYMBOL[k]}" for k in (2, 1, 0, -1, -2) if (s == k).any()
    )


def _value_cell(rec: pd.Series, lat: pd.Series, decimals: int) -> str:
    what = rec.get("measure_text") or ""
    if what:
        short = what.removeprefix("% thay đổi ").removesuffix(" năm trước")
        return (
            f"{monitor._value(rec.get('measured'), '%', 1)}"
            f'<div class="mv-meta">{html.escape(short)}</div>'
        )
    return monitor._value(lat["value"], lat["unit"], decimals)


GOOD, BAD, FLAT = "#1E7B34", "#B3261E", "#5F6B73"


def _plan_cells(rec: pd.Series, unit: str, decimals: int = 2) -> str:
    """Hai ô Kế hoạch / Dự báo và Xu hướng."""
    value = rec.get("fwd_value")
    if value is None or pd.isna(value):
        return '<td class="mv-val"><span class="mi-none">–</span></td><td class="sc-trend m-hide"></td>'
    src = str(rec.get("fwd_source") or "")
    src = "FedWatch" if src.startswith("FedWatch") else src
    when = str(rec.get("fwd_when") or "").replace("mục tiêu ", "").replace("kỳ ", "")
    if when.startswith("họp "):  # chỉ giữ tháng/năm, ngày đủ nằm trong tooltip
        when = when[-7:]
    tip = html.escape(f"{rec.get('fwd_source', '')}: {rec.get('fwd_text', '')}")
    target = rec.get("fwd_kind") == "target"
    shown = monitor._value(
        value, unit, 1 if target and float(value).is_integer() and unit == "%" else decimals
    )
    plan = f'<td class="mv-val" title="{tip}">{shown}<div class="mv-meta">{html.escape(src)} · {html.escape(when)}</div></td>'
    change = rec.get("fwd_change")
    if change is None or pd.isna(change):
        return plan + '<td class="sc-trend m-hide"></td>'
    better = rec.get("fwd_better")
    color = GOOD if better == 1 else BAD if better == -1 else FLAT
    arrow = "▲" if change > 0 else "▼" if change < 0 else "▶"
    actual = rec.get("fwd_actual")
    if rec.get("fwd_kind") == "target" and unit not in ("%", "điểm %") and actual and value:
        pct = actual / value * 100  # số tuyệt đối: tính % hoàn thành kế hoạch
        return plan + (
            f'<td class="sc-trend m-hide" style="color:{FLAT}" title="Thực tế / kế hoạch">'
            f"đạt {fmt.number(pct, 1)}% KH</td>"
        )
    if unit == "%":
        txt = f"{fmt.signed(change, 2)} điểm %"
    else:
        actual = rec.get("fwd_actual")
        txt = f"{fmt.signed(change / actual * 100, 1)}%" if actual else ""
    meaning = {1: "dự báo tốt hơn hiện tại", -1: "dự báo xấu hơn hiện tại"}.get(
        better, "cùng mức với hiện tại"
    )
    return (
        plan + f'<td class="sc-trend m-hide" style="color:{color}" title="{meaning}">'
        f'<span class="sc-arrow">{arrow}</span>{txt}</td>'
    )


def _indicator_row(rec: pd.Series, lat: pd.Series, decimals: int, spark: str) -> str:
    name = html.escape(lat["name"])
    meta = f"{fmt.period(lat['period'], lat['frequency'])} · {html.escape(lat['source'])}"
    stale = bool(rec.get("stale"))
    info = bool(rec.get("info"))
    level = rec["label"] or "chưa chấm"
    flags = [
        x for x in ("số cũ, không tính" if stale else "", "chỉ tham khảo" if info else "") if x
    ]
    status = rec["status"] if rec["status"] in SCORE_STATUS.values() else None
    raw_score = rec["score"]
    if pd.isna(raw_score) and status:  # số cũ: hiện mức cuối, làm mờ
        raw_score = {v: k for k, v in SCORE_STATUS.items()}.get(status)
    detail = ". ".join(x for x in (level, rec.get("detail") or "", *flags) if x)
    now = _box(raw_score, detail, status, muted=stale or info)
    if rec.get("show_level") is False:  # số lũy kế chỉ so với kế hoạch
        now = '<td class="mi-cell"><span class="mi-none">–</span></td>'
    weight = "tham khảo" if info else f"{fmt.number(rec['weight'] * 100, 0)}%"
    note = f'<div class="mv-meta sc-flag">{" · ".join(flags)}</div>' if flags else ""
    return (
        "<tr>"
        f'<td class="mv-name"><a href="detail?code={rec["code"]}" target="_self" title="{name}">{name}</a>'
        f'<div class="mv-meta">{meta}</div>{note}</td>'
        f'<td class="mv-spark m-hide">{spark}</td>'
        f'<td class="mv-val">{_value_cell(rec, lat, decimals)}</td>'
        f"{_plan_cells(rec, lat['unit'], decimals)}"
        f"{now}"
        f'<td class="r mv-meta m-hide">{weight}</td>'
        "</tr>"
    )


def table_html(  # noqa: PLR0913
    rows: pd.DataFrame,
    latest: pd.DataFrame,
    catalog: dict,
    group_names: dict,
    *,
    total: dict | None = None,
    sparks: dict | None = None,
) -> str:
    """Bảng scorecard: dòng tổng hợp, trụ cột, từng chỉ số."""
    lat = latest.set_index("code")
    sparks = sparks or {}
    cols = (
        '<colgroup><col><col style="width:84px"><col style="width:104px"><col style="width:120px">'
        '<col style="width:112px"><col style="width:62px"><col style="width:64px"></colgroup>'
    )
    head = (
        '<tr><th></th><th class="m-hide">Diễn biến</th><th class="r">Thực tế</th>'
        '<th class="r">Kế hoạch / Dự báo</th><th class="m-hide">Xu hướng</th>'
        '<th class="c">Mức</th><th class="r m-hide">Trọng số</th></tr>'
    )
    key = "pillar" if "pillar" in rows else "group"
    scored = rows[~rows["info"].astype(bool)] if "info" in rows else rows
    body = []
    for group in dict.fromkeys(rows[key]):
        part = rows[rows[key] == group]
        sp = scored[scored[key] == group]
        have = sp["score"].notna()
        weight = sp.loc[have, "weight"].sum()
        avg = (
            float((sp.loc[have, "score"] * sp.loc[have, "weight"]).sum() / weight)
            if weight
            else float("nan")
        )
        contrib = sp["contribution"].sum(min_count=1)
        contrib_txt = "chưa có số" if pd.isna(contrib) else f"đóng góp {fmt.signed(contrib, 2)}"
        name = html.escape(group_names.get(group, group))
        avg_tip = "" if pd.isna(avg) else f"Điểm trung bình trụ cột {fmt.signed(avg, 2)}"
        body.append(
            f'<tr class="mi-group"><td colspan="3"><b>{name}</b>'
            f'<span class="mi-gnote">{len(sp)} chỉ số · {contrib_txt}</span></td><td class="m-hide"></td><td class="m-hide"></td>'
            f"{_box(avg, avg_tip)}"
            f'<td class="r mv-meta m-hide">{fmt.number(sp["weight"].sum() * 100, 0)}%</td></tr>'
        )
        for _, rec in part.iterrows():
            if rec["code"] in lat.index:
                ind = catalog[rec["code"]]
                body.append(
                    _indicator_row(
                        rec, lat.loc[rec["code"]], ind.decimals, sparks.get(rec["code"], "")
                    )
                )
    total_row = ""
    if total is not None:
        score = total.get("score")
        shown = score if pd.notna(score) else total.get("last_score")
        rating = total["rating"] if pd.notna(score) else total.get("last_rating", "")
        when = "" if pd.notna(score) else f" (tháng {pd.Timestamp(total['last_date']):%m/%Y})"
        score_txt = "—" if pd.isna(shown) else f"{fmt.signed(shown, 2)}{when}"
        total_row = (
            f'<tr class="mi-total"><td colspan="3"><b>Tổng hợp</b>'
            f"<span class='mi-gnote'>{html.escape(str(rating))} · điểm {score_txt} · "
            f"{_counts(scored['score'])}</span></td>"
            '<td class="m-hide"></td><td class="m-hide"></td>'
            f'{_box(shown, str(rating), RATING_COLOR.get(rating))}<td class="m-hide"></td></tr>'
        )
    return f'<div class="sc-wrap"><table class="mv mi">{cols}{head}{total_row}{"".join(body)}</table></div>'


def history_chart(hist: pd.DataFrame, bands: list[dict], title: str) -> go.Figure:
    fig = go.Figure()
    scores = hist["score"].dropna()
    # Trục y theo khoảng điểm thực tế để dải hẹp vẫn đọc được.
    lo = max(-2.2, min(float(scores.min()) if len(scores) else -1.0, -0.6) - 0.2)
    hi = min(2.2, max(float(scores.max()) if len(scores) else 1.0, 1.1) + 0.2)
    edges = [b["min"] for b in bands]  # giảm dần
    tops = [hi, *edges[:-1]]
    for top, band in zip(tops, bands, strict=True):
        y0, y1 = max(band["min"], lo), min(top, hi)
        if y1 <= y0:
            continue
        bg = t.STATUS_COLORS.get(RATING_COLOR.get(band["label"], "none"))[0]
        tall = (y1 - y0) >= 0.09 * (hi - lo)
        label = (  # không truyền None: Plotly sẽ ghi "new text"
            {
                "annotation_text": band["label"],
                "annotation_position": "top right",
                "annotation_font": {"size": 10, "color": t.MUTED},
            }
            if tall
            else {}
        )
        fig.add_hrect(y0=y0, y1=y1, fillcolor=bg, opacity=0.6, line_width=0, layer="below", **label)
    fig.add_trace(
        go.Scatter(
            x=hist["date"],
            y=hist["score"],
            mode="lines",
            name="Điểm",
            line={"color": t.HEADING, "width": 2},
            hovertemplate="%{x|%m/%Y}: %{y:+.2f}<extra></extra>",
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
    t.apply_theme(fig, title, "điểm", height=320)
    fig.update_layout(showlegend=False, yaxis_range=[lo, hi])
    return fig


def fed_path_html(path: pd.DataFrame, current_upper: float, n: int = 8) -> str:
    """Bảng kỳ họp FOMC: biên trên kỳ vọng, chênh so với hiện tại, khoảng xác suất cao nhất."""
    if path.empty:
        return ""
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
        '<table class="mv mi sc-fed"><tr><th>Kỳ họp</th><th class="r">Biên trên kỳ vọng</th>'
        '<th class="r">So hiện tại</th><th>Khả năng cao nhất</th></tr>'
        f"{''.join(rows)}</table>"
        f"<p class='mc-note'>{src}, ngày {asof:%d/%m/%Y}. Biên trên kỳ vọng = bình quân "
        "theo xác suất. Là kỳ vọng thị trường, không phải dự báo của Fed.</p>"
    )


def forecast_map_html(df: pd.DataFrame) -> str:
    """Bảng thực tế so với kế hoạch / dự báo. Màu chênh lệch theo chiều tốt của chỉ số."""
    head = (
        '<colgroup><col><col style="width:110px"><col style="width:150px"><col style="width:130px">'
        '<col style="width:34%"></colgroup>'
        '<tr><th>Chỉ số thực tế</th><th class="r">Thực tế</th><th class="r">Kế hoạch / Dự báo</th>'
        '<th>Chênh</th><th class="m-hide">Ghi chú</th></tr>'
    )
    body = []
    for _, r in df.iterrows():
        unit = r["unit"]
        actual = monitor._value(r["actual"], unit, 2 if unit in ("%", "điểm %") else 0)
        when_actual = (
            fmt.period(r["actual_date"], r["frequency"]) if pd.notna(r["actual_date"]) else ""
        )
        if r["error"]:
            plan = f'<span class="sc-warn">{html.escape(r["error"])}</span>'
            change = ""
        elif pd.isna(r["plan"]):
            plan, change = '<span class="mi-none">chưa có số</span>', ""
        else:
            when = str(r["plan_when"]).replace("mục tiêu ", "").replace("kỳ ", "")
            plan = (
                f'{monitor._value(r["plan"], unit, 2 if unit in ("%", "điểm %") else 0)}<div class="mv-meta">'
                f"{html.escape(r['label'])} · {html.escape(when)}</div>"
            )
            change = _change_html(
                r["change"], unit, r["direction"], r["actual"], plan=r["plan"], kind=r["kind"]
            )
        tip = html.escape(f"{r['plan_source']}: {r['others']}") if r["others"] else ""
        body.append(
            f'<tr><td class="mv-name"><a href="detail?code={r["code"]}" target="_self">'
            f'{html.escape(r["name"])}</a><div class="mv-meta m-hide">{html.escape(str(r["code"]))}</div></td>'
            f'<td class="mv-val">{actual}<div class="mv-meta">{when_actual}</div></td>'
            f'<td class="mv-val" title="{tip}">{plan}</td>'
            f'<td class="sc-trend">{change}</td>'
            f'<td class="mv-meta m-hide">{html.escape(r["note"])}</td></tr>'
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
