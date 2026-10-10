"""Tính chuỗi từng chỉ số từ store raw dài [series_id, date, value, source] theo `recipe`.

Giữ cột source theo từng dòng để bản công khai lọc bỏ được dòng Yahoo.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from macro_app.config import Indicator
from macro_app.metrics import transforms as tf

DERIVED_SOURCE = "Tính toán"


@dataclass
class RawContext:
    store: pd.DataFrame
    deposit_panel: pd.DataFrame | None = None
    banks: pd.DataFrame | None = None
    manual: pd.DataFrame = field(default_factory=pd.DataFrame)


def raw_frame(store: pd.DataFrame, series_id: str) -> pd.DataFrame:
    part = store[store["series_id"] == series_id]
    if part.empty:
        return pd.DataFrame(columns=["value", "source"], index=pd.DatetimeIndex([], name="date"))
    frame = part.drop_duplicates("date", keep="last").set_index("date").sort_index()
    return frame[["value", "source"]]


def _with_source(values: pd.Series, source: str) -> pd.DataFrame:
    values = values.dropna()
    frame = pd.DataFrame({"value": values, "source": source})
    frame.index.name = "date"
    return frame


def _main_source(frame: pd.DataFrame) -> str:
    return frame["source"].iloc[-1] if not frame.empty else ""


def _op_raw(ind: Indicator, ctx: RawContext, _done: dict) -> pd.DataFrame:
    return raw_frame(ctx.store, ind.recipe["input"])


def _op_extend(ind: Indicator, ctx: RawContext, _done: dict) -> pd.DataFrame:
    primary, secondary = (raw_frame(ctx.store, sid) for sid in ind.recipe["inputs"])
    if primary.empty:
        return secondary
    tail = secondary[secondary.index > primary.index.max()]
    return pd.concat([primary, tail])


def _level_op(fn: Callable[[pd.Series], pd.Series]) -> Callable:
    def op(ind: Indicator, ctx: RawContext, _done: dict) -> pd.DataFrame:
        frame = raw_frame(ctx.store, ind.recipe["input"])
        return _with_source(fn(frame["value"], ind), _main_source(frame))

    return op


def _op_published_or_mom_yoy(ind: Indicator, ctx: RawContext, _done: dict) -> pd.DataFrame:
    """YoY ưu tiên số công bố; tháng không có số công bố mới tính từ chuỗi MoM.

    File 07_CPI nhập nhầm MoM ở T12/2022 và T1/2023 nên chuỗi tự tính lệch cả năm 2023.
    """
    published = raw_frame(ctx.store, ind.recipe["published"])
    mom = raw_frame(ctx.store, ind.recipe["input"])
    calc = _with_source(tf.mom_to_yoy(mom["value"]), _main_source(mom))
    return pd.concat([published, calc[~calc.index.isin(published.index)]]).sort_index()


def _op_deposit(ind: Indicator, ctx: RawContext, _done: dict) -> pd.DataFrame:
    from macro_app.metrics.deposit import deposit_average

    if ctx.deposit_panel is None or ctx.banks is None:
        return _with_source(pd.Series(dtype=float), "Simplize")
    values = deposit_average(
        ctx.deposit_panel,
        ctx.banks,
        tenor_m=int(ind.recipe.get("tenor_m", 12)),
        bank_group=ind.recipe.get("bank_group", "big4"),
    )
    return _with_source(values, "Simplize")


def _op_diff(ind: Indicator, _ctx: RawContext, done: dict) -> pd.DataFrame:
    left_code, right_code = ind.recipe["inputs"]
    left, right = done.get(left_code), done.get(right_code)
    if left is None or right is None:
        return _with_source(pd.Series(dtype=float), DERIVED_SOURCE)
    values = tf.align_diff(left["value"], right["value"], ind.frequency)
    return _with_source(values, DERIVED_SOURCE)


def _op_raw_diff(ind: Indicator, ctx: RawContext, _done: dict) -> pd.DataFrame:
    """Hiệu hai chuỗi gốc cùng kỳ, vd xuất khẩu − nhập khẩu = cán cân thương mại."""
    left, right = (raw_frame(ctx.store, sid)["value"] for sid in ind.recipe["inputs"])
    return _with_source(
        tf.align_diff(left, right, ind.frequency),
        _main_source(raw_frame(ctx.store, ind.recipe["inputs"][0])),
    )


def _op_raw_ratio(ind: Indicator, ctx: RawContext, _done: dict) -> pd.DataFrame:
    """Tỷ lệ % hai chuỗi gốc cùng kỳ, vd dư nợ tín dụng / M2 (đại diện LDR)."""
    a, b = (
        tf.to_period(raw_frame(ctx.store, sid)["value"], ind.frequency)
        for sid in ind.recipe["inputs"]
    )
    return _with_source((a / b * 100).dropna(), DERIVED_SOURCE)


def _op_product(ind: Indicator, _ctx: RawContext, done: dict) -> pd.DataFrame:
    """a × b × scale trên ngày chung, vd Brent (USD/thùng) × tỷ giá → VND/thùng."""
    left_code, right_code = ind.recipe["inputs"]
    left, right = done.get(left_code), done.get(right_code)
    if left is None or right is None:
        return _with_source(pd.Series(dtype=float), DERIVED_SOURCE)
    a = tf.to_period(left["value"], ind.frequency)
    b = tf.to_period(right["value"], ind.frequency)
    values = (a * b * float(ind.recipe.get("scale", 1.0))).dropna()
    return _with_source(values, DERIVED_SOURCE)


def _op_manual(ind: Indicator, ctx: RawContext, _done: dict) -> pd.DataFrame:
    m = ctx.manual
    if m.empty:
        return _with_source(pd.Series(dtype=float), "Nhập tay")
    part = m[m["code"] == ind.code].copy()
    part["date"] = pd.to_datetime(part["date"])
    part = part.sort_values(["date", "entered_at"]).drop_duplicates("date", keep="last")
    frame = part.set_index("date")[["value", "method"]].rename(columns={"method": "source"})
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["source"] = frame["source"].map(
        {"manual": "Nhập tay", "ai_suggested_confirmed": "AI gợi ý, đã xác nhận"}
    )
    return frame.dropna(subset=["value"])


def _op_raw_manual(ind: Indicator, ctx: RawContext, done: dict) -> pd.DataFrame:
    """Chuỗi từ nguồn tự động, bổ sung / sửa bằng dòng nhập tay cùng mã (nhập tay thắng cùng kỳ)."""
    auto = raw_frame(ctx.store, ind.recipe["input"])
    manual = _op_manual(ind, ctx, done)
    if manual.empty:
        return auto
    return pd.concat([auto[~auto.index.isin(manual.index)], manual]).sort_index()


def plans_for(code: str) -> dict[int, float]:
    """Kế hoạch năm của chỉ số lũy kế, lấy từ dòng nhập tay theo năm trong forecast_map."""
    from macro_app.metrics.forward import load_forecast_map

    out = {}
    for m in load_forecast_map():
        period = str(m.get("period") or "").strip()
        if m.get("code") == code and m.get("kind") == "manual" and period.isdigit():
            out[int(period)] = float(m["value"])
    return out


def _op_plan_pace(ind: Indicator, ctx: RawContext, _done: dict) -> pd.DataFrame:
    flow = raw_frame(ctx.store, ind.recipe["input"])["value"]
    plans = plans_for(ind.recipe["plans_from"])
    if flow.empty or not plans:
        return _with_source(pd.Series(dtype=float), DERIVED_SOURCE)
    return _with_source(tf.plan_pace(flow, plans), DERIVED_SOURCE)


OPS: dict[str, Callable] = {
    "raw": _op_raw,
    "extend": _op_extend,
    "yoy": _level_op(lambda s, ind: tf.yoy_pct(s, ind.frequency)),
    "mom_to_yoy": _level_op(lambda s, _ind: tf.mom_to_yoy(s)),
    "published_or_mom_yoy": _op_published_or_mom_yoy,
    "mom_to_avg_ytd": _level_op(lambda s, _ind: tf.mom_to_avg_ytd(s)),
    "ytd_change_pct": _level_op(lambda s, _ind: tf.ytd_change_pct(s)),
    "ytd_sum_yoy": _level_op(lambda s, _ind: tf.ytd_sum_yoy(s)),
    "ytd_sum": _level_op(lambda s, _ind: tf.ytd_sum(s)),
    "plan_pace": _op_plan_pace,
    "ytd_to_yoy": _level_op(lambda s, _ind: tf.ytd_to_yoy(s)),
    "quarter_last": _level_op(lambda s, _ind: tf.quarter_end_values(s)),
    "deposit_avg": _op_deposit,
    "diff": _op_diff,
    "product": _op_product,
    "raw_diff": _op_raw_diff,
    "raw_ratio": _op_raw_ratio,
    "manual": _op_manual,
    "raw_manual": _op_raw_manual,
}


def compute_indicator(ind: Indicator, ctx: RawContext, done: dict) -> pd.DataFrame:
    op = ind.recipe.get("op")
    if op not in OPS:
        raise ValueError(f"{ind.code}: recipe op không hỗ trợ: {op}")
    frame = OPS[op](ind, ctx, done)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    frame.index = pd.DatetimeIndex(frame.index).normalize()
    frame.index.name = "date"
    return frame.dropna(subset=["value"])


def compute_all(indicators: list[Indicator], ctx: RawContext) -> dict[str, pd.DataFrame]:
    """Tính chỉ số thường trước, chỉ số dẫn xuất (`diff`, `product`) sau."""
    done: dict[str, pd.DataFrame] = {}
    ordered = sorted(indicators, key=lambda i: i.recipe.get("op") in ("diff", "product"))
    for ind in ordered:
        done[ind.code] = compute_indicator(ind, ctx, done)
    return done


def rebase_input(ind: Indicator, ctx: RawContext) -> pd.Series | None:
    """Chuỗi mức gốc dùng để dò 'nghi đổi năm gốc' (chỉ recipe yoy)."""
    if ind.recipe.get("op") != "yoy":
        return None
    return raw_frame(ctx.store, ind.recipe["input"])["value"]
