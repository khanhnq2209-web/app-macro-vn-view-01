"""LS huy động bình quân nhóm NH: lịch ngày + ffill có giới hạn (D4)."""

from __future__ import annotations

import pandas as pd
import pytest

from macro_app.metrics.deposit import deposit_average
from macro_app.paths import BANKS_FILE, DEPOSIT_FILE

BANKS = pd.DataFrame(
    {
        "bank_code": ["A", "B", "C"],
        "is_big4": [True, True, False],
        "is_big10": [True, True, True],
    }
)


def _panel(rows: list[tuple[str, str, int, float]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["date", "bank_code", "tenor_m", "rate_pct"])
    return frame.assign(date=pd.to_datetime(frame["date"]))


def test_ffill_each_bank_before_averaging():
    panel = _panel(
        [
            ("2024-01-01", "A", 12, 5.0),
            ("2024-01-03", "B", 12, 7.0),
            ("2024-01-05", "A", 12, 6.0),
            ("2024-01-03", "A", 6, 99.0),  # kỳ hạn khác — bỏ
        ]
    )
    avg = deposit_average(panel, BANKS, tenor_m=12, bank_group="big4")
    assert avg.index.equals(pd.date_range("2024-01-01", "2024-01-05", freq="D", name="date"))
    assert avg.tolist() == pytest.approx([5.0, 5.0, 6.0, 6.0, 6.5])
    assert avg.name == "deposit_12m_big4"


def test_ffill_limit_expires_stale_quote():
    panel = _panel([("2024-01-01", "A", 12, 5.0), ("2024-01-10", "B", 12, 7.0)])
    avg = deposit_average(panel, BANKS, ffill_limit_days=3)
    assert avg[pd.Timestamp("2024-01-04")] == 5.0
    assert pd.Timestamp("2024-01-05") not in avg.index  # A hết hạn, B chưa báo giá → bỏ ngày
    assert avg[pd.Timestamp("2024-01-10")] == 7.0


def test_bank_group_filter_and_invalid_group():
    panel = _panel([("2024-01-01", "A", 12, 5.0), ("2024-01-01", "C", 12, 9.0)])
    assert deposit_average(panel, BANKS, bank_group="big4").iloc[0] == 5.0
    assert deposit_average(panel, BANKS, bank_group="all").iloc[0] == 7.0
    with pytest.raises(ValueError, match="bank_group"):
        deposit_average(panel, BANKS, bank_group="top3")


def test_empty_selection_returns_empty_series():
    panel = _panel([("2024-01-01", "C", 12, 9.0)])
    assert deposit_average(panel, BANKS, bank_group="big4").empty


@pytest.mark.skipif(not DEPOSIT_FILE.exists(), reason="không có file 01")
def test_golden_real_panel():
    from macro_app.io.vn_raw import load_banks, load_deposit_panel

    panel, banks = load_deposit_panel(), load_banks()
    assert panel["bank_code"].nunique() == 20
    assert set(panel["tenor_m"]) == {1, 3, 6, 9, 12, 24}
    big4 = set(banks.loc[banks["is_big4"], "bank_code"])
    # Ngày đầu tiên: cả 4 NH Big4 cùng báo giá → bình quân = trung bình thẳng ngày đó
    first = panel["date"].min()
    day = panel[panel["date"].eq(first) & panel["tenor_m"].eq(12) & panel["bank_code"].isin(big4)]
    assert len(day) == 4
    avg = deposit_average(panel, banks, tenor_m=12, bank_group="big4")
    assert avg.iloc[0] == pytest.approx(day["rate_pct"].mean())
    assert avg.between(2, 12).all()
    assert BANKS_FILE.exists()
