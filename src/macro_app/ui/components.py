"""Thành phần dùng chung: chart theo view, bảng số liệu, nút tải, chân trang."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from macro_app import fmt
from macro_app.charts.series import ChartSpec, SeriesSpec, build_chart
from macro_app.config import load_thresholds
from macro_app.metrics.quality import FLAG_LABEL
from macro_app.metrics.status import STATUS_LABEL, resolve_threshold
from macro_app.ui import data

FOOTER_HIDDEN = "Bản công khai không hiển thị số liệu có bản quyền (Yahoo, LME)."
FOOTER_SHOWN = "Số liệu Yahoo Finance và LME (Westmetall) chỉ dùng nội bộ, không phát hành lại."


def threshold_bands(code: str) -> dict:
    default, overrides = load_thresholds()
    cfg, _ = resolve_threshold(code, default, overrides)
    if cfg.get("method") != "absolute":
        return {}
    return {"green": cfg.get("green"), "yellow": cfg.get("yellow")}


def target_step(target_id: str | None) -> pd.Series | None:
    if not target_id:
        return None
    yearly = data.target_series(target_id, data.build_stamp())
    if yearly.empty:
        return None
    starts = pd.to_datetime([f"{d.year}-01-01" for d in yearly.index])
    ends = pd.to_datetime([f"{d.year}-12-31" for d in yearly.index])
    return pd.concat(
        [pd.Series(yearly.to_numpy(), index=starts), pd.Series(yearly.to_numpy(), index=ends)]
    ).sort_index()


def _add_forward(fig, history: pd.Series, forward: pd.Series, name: str) -> None:
    """Nối đường kỳ vọng từ điểm cuối của chuỗi thật."""
    import plotly.graph_objects as go

    from macro_app.charts import theme

    if history.empty:
        return
    x = [history.index[-1], *forward.index]
    y = [float(history.iloc[-1]), *forward.to_numpy()]
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="lines+markers",
            name=name,
            line={"color": theme.HIGHLIGHT, "width": 2, "dash": "dot"},
            marker={"size": 6},
            hovertemplate="%{x|%d/%m/%Y}: %{y:.2f}<extra>" + name + "</extra>",
        )
    )


def chart_from_view(chart: dict, *, key: str, overrides: dict | None = None) -> None:
    cfg = {**chart, **(overrides or {})}
    catalog = data.catalog_map()
    codes = [c for c in cfg.get("codes", []) if c in catalog]
    secondary = set(cfg.get("secondary") or [])
    specs = [
        SeriesSpec(
            code=c,
            name=catalog[c].name,
            unit=catalog[c].unit,
            frequency=catalog[c].frequency,
            change_unit=catalog[c].change_unit,
            values=data.series(c),
            secondary=c in secondary,
        )
        for c in codes
    ]
    first = catalog[codes[0]] if codes else None
    spec = ChartSpec(
        title=cfg.get("title", ""),
        series=specs,
        kind=cfg.get("kind", "line"),
        range=cfg.get("range", "5Y"),
        transform=cfg.get("transform", "level"),
        target=target_step(first.target) if first and cfg.get("show_target") else None,
        bands=threshold_bands(codes[0]) if codes and cfg.get("show_bands") else {},
    )
    fig = build_chart(spec)
    forward = cfg.get("forward")
    if forward is not None and not forward.empty and spec.transform == "level" and specs:
        _add_forward(
            fig, data.series(codes[0]).dropna(), forward, cfg.get("forward_name", "Kỳ vọng")
        )
    st.plotly_chart(fig, width="stretch", key=key, config={"displayModeBar": False})
    if cfg.get("note"):
        st.caption(cfg["note"])


def stats_table(codes: list[str]) -> None:
    latest = data.latest()
    catalog = data.catalog_map()
    part = (
        latest[latest["code"].isin(codes)]
        .set_index("code")
        .reindex(codes)
        .dropna(how="all")
        .reset_index()
    )
    if part.empty:
        st.caption("Chưa có dữ liệu")
        return
    rows = []
    for rec in part.to_dict("records"):
        ind = catalog[rec["code"]]
        rows.append(
            {
                "Chỉ số": rec["name"],
                "Giá trị": fmt.value(rec["value"], rec["unit"], ind.decimals),
                "Kỳ": fmt.period(rec["period"], rec["frequency"]),
                "So cùng kỳ": fmt.change(rec["yoy_change"], rec["change_unit"]),
                "Từ đầu năm": fmt.change(rec["ytd_change"], rec["change_unit"]),
                "So mục tiêu": fmt.signed(rec["vs_target"])
                if pd.notna(rec["vs_target"])
                else fmt.MISSING,
                "Z-score 5 năm": fmt.number(rec["zscore_5y"], 2),
                "Trạng thái": STATUS_LABEL.get(rec["status"], rec["status"]),
                "Cờ": ", ".join(
                    FLAG_LABEL[f] for f in str(rec["flags"]).split(";") if f in FLAG_LABEL
                ),
                "Nguồn": rec["source"],
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def download_series_button(codes: list[str], key: str) -> None:
    frames = [data.series_frame(c).assign(code=c) for c in codes]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return
    df = pd.concat(frames)
    df = df[df["source"] != "Yahoo"] if data.hide_vendor() else df
    st.download_button(
        "Tải CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{'_'.join(codes)[:60]}.csv",
        mime="text/csv",
        key=key,
    )


def footer() -> None:
    meta = data.build_meta()
    built = meta.get("built_at", "")[:16].replace("T", " ")
    note = FOOTER_HIDDEN if data.hide_vendor() else FOOTER_SHOWN
    st.html(f'<div class="mc-footer">{note} Cập nhật {built}.</div>')
