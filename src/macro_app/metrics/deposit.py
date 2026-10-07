"""Lãi suất huy động bình quân nhóm NH.

Số NH có quan sát mỗi ngày dao động 6 đến 20 nên bình quân thẳng tạo bước nhảy giả. Vì vậy
mỗi NH giữ báo giá gần nhất tối đa `ffill_limit_days` ngày lịch rồi mới bình quân.
"""

from __future__ import annotations

import pandas as pd

BANK_GROUPS = {"big4": "is_big4", "big10": "is_big10", "all": None}


def select_banks(banks: pd.DataFrame, bank_group: str) -> pd.Index | None:
    """Mã NH thuộc nhóm; None = mọi NH."""
    if bank_group not in BANK_GROUPS:
        raise ValueError(f"bank_group phải thuộc {sorted(BANK_GROUPS)}, nhận '{bank_group}'")
    flag = BANK_GROUPS[bank_group]
    if flag is None:
        return None
    return pd.Index(banks.loc[banks[flag].astype(bool), "bank_code"])


def bank_calendar(panel: pd.DataFrame, ffill_limit_days: int) -> pd.DataFrame:
    """Bảng ngày x NH, báo giá mỗi NH điền xuôi tối đa `ffill_limit_days` ngày lịch."""
    wide = panel.pivot_table(index="date", columns="bank_code", values="rate_pct", aggfunc="last")
    days = pd.date_range(wide.index.min(), wide.index.max(), freq="D", name="date")
    return wide.reindex(days).ffill(limit=ffill_limit_days)


def deposit_average(
    panel: pd.DataFrame,
    banks: pd.DataFrame,
    tenor_m: int = 12,
    bank_group: str = "big4",
    ffill_limit_days: int = 90,
) -> pd.Series:
    """Chuỗi ngày LS huy động bình quân nhóm NH cho kỳ hạn `tenor_m` (%)."""
    name = f"deposit_{tenor_m}m_{bank_group}"
    codes = select_banks(banks, bank_group)
    sub = panel[panel["tenor_m"].eq(tenor_m)].dropna(subset=["rate_pct"])
    if codes is not None:
        sub = sub[sub["bank_code"].isin(codes)]
    if sub.empty:
        return pd.Series(dtype=float, name=name, index=pd.DatetimeIndex([], name="date"))
    average = bank_calendar(sub, ffill_limit_days).mean(axis=1, skipna=True)
    return average.dropna().rename(name)
