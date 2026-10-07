"""Bảng hiển thị FedWatch từ dạng dài [asof, meeting_date, range_low_bp, range_high_bp, prob]."""

from __future__ import annotations

import pandas as pd


def range_label(low_bp: int, high_bp: int) -> str:
    return f"{low_bp / 100:.2f}–{high_bp / 100:.2f}".replace(".", ",")


def latest_asof(df: pd.DataFrame) -> pd.Timestamp | None:
    return None if df.empty else pd.to_datetime(df["asof"]).max()


def matrix(df: pd.DataFrame, asof: pd.Timestamp | None = None) -> pd.DataFrame:
    """Hàng = kỳ họp, cột = khoảng lãi suất (thấp → cao), giá trị = xác suất (0–1)."""
    if df.empty:
        return pd.DataFrame()
    d = df.copy()
    d["asof"] = pd.to_datetime(d["asof"])
    d = d[d["asof"] == (asof or d["asof"].max())]
    d = d[d["prob"] > 0.0005]
    d = d.sort_values("range_low_bp")
    d["range"] = [
        range_label(lo, hi) for lo, hi in zip(d["range_low_bp"], d["range_high_bp"], strict=True)
    ]
    order = list(dict.fromkeys(d["range"]))
    out = d.pivot_table(
        index="meeting_date", columns="range", values="prob", aggfunc="sum"
    ).reindex(columns=order)
    out.index = pd.to_datetime(out.index)
    return out.sort_index()


def summary(df: pd.DataFrame, ranges: pd.DataFrame) -> pd.DataFrame:
    """Mỗi (asof, kỳ họp): P(giảm/giữ/tăng) so với khoảng hiện tại + khoảng khả năng cao nhất."""
    if df.empty:
        return pd.DataFrame()
    d = df.copy()
    d["asof"] = pd.to_datetime(d["asof"])
    d["meeting_date"] = pd.to_datetime(d["meeting_date"])
    # ranges [date, low_bp, high_bp] = khoảng mục tiêu hiệu lực → lấy khoảng tại ngày asof
    r = ranges.sort_values("date").rename(
        columns={"date": "asof", "low_bp": "cur_low", "high_bp": "cur_high"}
    )
    d = pd.merge_asof(d.sort_values("asof"), r, on="asof", direction="backward")
    d["move"] = "hold"
    d.loc[d["range_high_bp"] < d["cur_high"], "move"] = "cut"
    d.loc[d["range_low_bp"] > d["cur_low"], "move"] = "hike"
    probs = d.pivot_table(
        index=["asof", "meeting_date"], columns="move", values="prob", aggfunc="sum"
    )
    probs = probs.reindex(columns=["cut", "hold", "hike"]).fillna(0.0)
    top = (
        d.sort_values("prob")
        .groupby(["asof", "meeting_date"])
        .tail(1)
        .set_index(["asof", "meeting_date"])
    )
    top = top.reindex(probs.index)
    probs["top_range"] = [
        range_label(lo, hi)
        for lo, hi in zip(top["range_low_bp"], top["range_high_bp"], strict=True)
    ]
    probs["top_prob"] = top["prob"]
    return probs.reset_index()
