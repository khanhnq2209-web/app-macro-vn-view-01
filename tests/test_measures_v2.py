"""Cách đo mới (trung bình trượt, tổng 12 tháng) và ngưỡng cứng hai phía."""

import numpy as np
import pandas as pd
import pytest

from macro_app.metrics import threshold_preview as tp
from macro_app.metrics.status import evaluate, validate_cfg
from macro_app.metrics.transforms import measure

BELL = {"method": "absolute", "cuts": [8, 11, 15, 18], "side": "both"}


def monthly(values, start="2020-01-31"):
    return pd.Series(
        values, index=pd.date_range(start, periods=len(values), freq="ME"), dtype=float
    )


def test_mean_by_points_needs_full_window():
    s = pd.Series(
        [1, 2, 3, 4, 100], index=pd.date_range("2026-01-01", periods=5, freq="D"), dtype=float
    )
    m = measure(s, "D", {"kind": "mean", "n": 3, "unit": "period"})
    assert m.tolist() == [2.0, 3.0, pytest.approx(107 / 3)]


def test_mean_by_calendar_days():
    idx = pd.date_range("2026-01-01", periods=40, freq="D")
    s = pd.Series(np.r_[np.full(30, 4.0), np.full(10, 17.0)], index=idx)
    m = measure(s, "D", {"kind": "mean", "n": 20, "unit": "day"})
    assert m.index[0] == pd.Timestamp("2026-01-20")
    assert m.iloc[-1] == pytest.approx((10 * 4 + 10 * 17) / 20)  # gai 17% bị làm mềm


def test_sum12_pct_from_monthly_flow():
    s = monthly([10.0] * 12 + [12.0] * 12)
    m = measure(s, "M", {"kind": "sum12_pct"})
    assert m.iloc[-1] == pytest.approx(20.0)
    assert m.index[0] == pd.Timestamp("2021-12-31")


def test_sum12_pct_from_ytd_cumulative():
    flow = [10.0] * 12 + [12.0] * 12
    ytd = (
        pd.Series(flow, index=pd.date_range("2020-01-31", periods=24, freq="ME"))
        .groupby(lambda d: d.year)
        .cumsum()
    )
    m = measure(ytd, "M", {"kind": "sum12_pct", "ytd": True})
    assert m.iloc[-1] == pytest.approx(20.0)


def test_sum12_pct_skips_gaps():
    s = monthly([10.0] * 24).drop(pd.Timestamp("2021-06-30"))
    m = measure(s, "M", {"kind": "sum12_pct"})
    assert pd.Timestamp("2021-12-31") not in m.index  # thiếu tháng 6/2021 → không tính


@pytest.mark.parametrize(
    ("value", "status"),
    [
        (13, "green_strong"),
        (11, "green_strong"),
        (15, "green_strong"),
        (9, "yellow"),
        (17, "yellow"),
        (7, "red"),
        (19, "red"),
    ],
)
def test_two_sided_hard_threshold(value, status):
    res = evaluate(monthly([value]), "M", BELL, "test")
    assert res.status == status


def test_two_sided_middle_is_inverse():
    res = evaluate(monthly([13]), "M", {**BELL, "side": "middle"}, "test")
    assert res.status == "red"


def test_two_sided_needs_even_cuts():
    assert validate_cfg({**BELL, "cuts": [8, 11, 15]})
    assert validate_cfg(BELL) == []


def test_two_sided_bands_for_chart():
    s = monthly([5.0, 25.0])
    got = [st for _, _, st in tp.bands(s, BELL, np.nan, 0, 30)]
    assert got == ["red", "yellow", "green_strong", "yellow", "red"]


def test_sum12_ytd_gap_invalidates_window():
    """Thiếu một tháng trong chuỗi lũy kế: cửa sổ chứa các tháng sau đó không được tính."""
    flow = pd.Series(1.0, index=pd.date_range("2021-01-31", periods=60, freq="ME"))
    ytd = flow.groupby(flow.index.year).cumsum().drop(pd.Timestamp("2023-02-28"))
    m = measure(ytd, "M", {"kind": "sum12_pct", "ytd": True})
    for bad in ("2024-02-29", "2025-02-28"):  # cửa sổ 12 tháng hoặc kỳ so sánh dính tháng thiếu
        assert pd.Timestamp(bad) not in m.index or abs(m[bad]) < 1e-9
    assert (m.dropna().abs() < 1e-9).all()  # mọi giá trị còn lại phải là 0% (số đều 1/tháng)


def test_sum12_ytd_series_starting_mid_year():
    flow = pd.Series(1.0, index=pd.date_range("2021-02-28", periods=47, freq="ME"))
    ytd = flow.groupby(flow.index.year).cumsum()  # năm đầu thiếu tháng 1
    m = measure(ytd, "M", {"kind": "sum12_pct", "ytd": True})
    assert (m.dropna().abs() < 1e-9).all()


def test_two_sided_odd_cuts_do_not_crash():
    res = evaluate(
        monthly([5.0]), "M", {"method": "absolute", "cuts": [1, 2, 3], "side": "both"}, "t"
    )
    assert res.status == "none"
    res = evaluate(monthly([5.0]), "M", {"method": "absolute", "cuts": [1, 2, 3]}, "t")
    assert res.status == "none"  # thiếu side → mặc định hai phía


def test_two_sided_distance_to_worse_cut():
    far = evaluate(monthly([20.0]), "M", BELL, "t")
    assert far.distance_to_next == 0  # đã vượt mốc ngoài cùng
    near = evaluate(monthly([16.0]), "M", BELL, "t")
    assert near.distance_to_next == pytest.approx(2.0)  # tới mốc 18


def test_ytd_sum_and_plan_pace():
    from macro_app.metrics.transforms import plan_pace, ytd_sum

    flow = monthly([10.0] * 12 + [20.0] * 9, start="2025-01-31")  # 2026: 9 tháng × 20
    cum = ytd_sum(flow)
    assert cum["2025-12-31"] == pytest.approx(120.0) and cum["2026-01-31"] == pytest.approx(20.0)
    pace = plan_pace(flow, {2026: 240.0})  # 9 tháng đạt 180/240 = 75% = đúng tiến độ
    assert pace["2026-09-30"] == pytest.approx(0.0)
    assert pace["2026-03-31"] == pytest.approx(60 / 240 * 100 - 25)
    assert pd.Timestamp("2025-06-30") not in pace.index  # năm không có kế hoạch → không tính


def test_ytd_sum_gap_blanks_rest_of_year():
    from macro_app.metrics.transforms import ytd_sum

    flow = monthly([1.0] * 12, start="2026-01-31").drop(pd.Timestamp("2026-03-31"))
    cum = ytd_sum(flow)
    assert pd.Timestamp("2026-02-28") in cum.index and pd.Timestamp("2026-04-30") not in cum.index
