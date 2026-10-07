"""Golden tests scorecard: trọng số, điểm tổng, thiếu dữ liệu, lịch sử không nhìn trước."""

import numpy as np
import pandas as pd
import pytest

from macro_app.config import load_catalog, load_thresholds
from macro_app.metrics import scorecard as sc

CAT = {i.code: i for i in load_catalog()}
SETTINGS = sc.load_settings()


def ctx(asof="2020-01-31"):
    return {
        "settings": SETTINGS,
        "asof": pd.Timestamp(asof),
        "min_points": load_thresholds()[0]["min_points"],
        "targets": {},
        "target_series": {},
    }


def monthly_frame(values, start="2020-01-31"):
    idx = pd.date_range(start, periods=len(values), freq="ME")
    return pd.DataFrame({"value": values, "source": "test"}, index=idx)


def test_weights_equal_by_group_then_within():
    rows = [{"code": "cpi_yoy"}, {"code": "fx_central_ytd"}, {"code": "credit_yoy"}]  # B2, B2, B4
    w = sc.weights(rows, CAT)
    assert w["credit_yoy"] == pytest.approx(0.5)
    assert w["cpi_yoy"] == pytest.approx(0.25)
    assert sum(w.values()) == pytest.approx(1.0)


def test_explicit_weights_are_normalised():
    rows = [{"code": "cpi_yoy", "weight": 3}, {"code": "credit_yoy", "weight": 1}]
    assert sc.weights(rows, CAT)["cpi_yoy"] == pytest.approx(0.75)


def test_current_score_and_rating():
    card = {
        "rows": [
            {
                "code": "cpi_yoy",
                "method": "absolute",
                "cuts": [2.5, 3.5, 4.5, 5.5],
                "side": "above",
            },
            {"code": "credit_yoy", "method": "absolute", "cuts": [10, 12, 15, 18], "side": "below"},
        ]
    }
    frames = {
        "cpi_yoy": monthly_frame([6.0]),
        "credit_yoy": monthly_frame([19.0]),
    }  # Rất xấu −2, Rất tốt +2
    table, total = sc.current(card, frames, CAT, ctx())
    assert table.set_index("code")["score"].to_dict() == {"cpi_yoy": -2.0, "credit_yoy": 2.0}
    assert total["score"] == pytest.approx(0.0)
    assert total["rating"] == "Bất lợi"  # 0 nằm dưới mốc Trung tính (0,05)


def test_missing_rows_reweight_and_coverage_floor():
    card = {
        "rows": [
            {
                "code": "cpi_yoy",
                "method": "absolute",
                "cuts": [2.5, 3.5, 4.5, 5.5],
                "side": "above",
            },
            {"code": "credit_yoy", "method": "absolute", "cuts": [10, 12, 15, 18], "side": "below"},
        ]
    }
    frames = {"cpi_yoy": monthly_frame([2.0])}  # chỉ còn 50% trọng số < 60% → không chấm
    _, total = sc.current(card, frames, CAT, ctx())
    assert np.isnan(total["score"]) and total["coverage"] == pytest.approx(0.5)
    assert total["rating"] == "Chưa đủ dữ liệu"


def test_history_uses_only_past_data():
    card = {
        "rows": [
            {"code": "cpi_yoy", "method": "absolute", "cuts": [2.5, 3.5, 4.5, 5.5], "side": "above"}
        ]
    }
    frames = {"cpi_yoy": monthly_frame([2.0] * 12 + [6.0] * 12)}
    h = sc.history(card, frames, CAT, ctx("2021-12-31")).set_index("date")
    assert h.loc["2020-12-31", "score"] == pytest.approx(2.0)  # trước cú tăng: Rất tốt
    assert h.loc["2021-12-31", "score"] == pytest.approx(-2.0)


def test_bundled_profile_bds01():
    """Bộ mặc định hợp lệ. Không gắn cứng số dòng/mô tả vì người dùng sửa bộ này trên app."""
    from macro_app import profiles

    all_profiles = profiles.load_profiles()
    assert "theo_doi_bds_01" in all_profiles
    prof = all_profiles["theo_doi_bds_01"]
    assert {"nha_o", "kcn"} <= set(prof["segments"])
    for slug, card in prof["segments"].items():
        assert card["rows"], slug
        assert sc.validate_card(card, CAT, SETTINGS) == [], slug
        assert all(r.get("pillar") for r in card["rows"]), slug


def test_rating_bands():
    bands = SETTINGS["rating_bands"]
    assert sc.rating(1.2, bands) == "Rất thuận lợi"
    assert sc.rating(0.45, bands) == "Thuận lợi"
    assert sc.rating(0.05, bands) == "Trung tính"
    assert sc.rating(0.0, bands) == "Bất lợi"
    assert sc.rating(-0.21, bands) == "Rất bất lợi"


def test_measure_pct_change_in_row():
    card = {
        "rows": [
            {
                "code": "brent",
                "method": "absolute",
                "cuts": [-10, 0, 10, 25],
                "side": "above",
                "measure": {"kind": "pct_change", "n": 90, "unit": "day"},
            }
        ]
    }
    idx = pd.date_range("2025-01-01", periods=200, freq="D")
    frame = pd.DataFrame(
        {"value": np.r_[np.full(170, 80.0), np.full(30, 104.0)], "source": "t"}, index=idx
    )
    table, _ = sc.current(card, {"brent": frame}, CAT, ctx("2025-07-31"))
    assert table.iloc[0]["label"] == "Rất xấu"  # +30% trong 90 ngày > 25%


CPI_ROW = {"code": "cpi_yoy", "method": "absolute", "cuts": [2.5, 3.5, 4.5, 5.5], "side": "above"}


def test_weights_follow_pillar_not_catalog_group():
    rows = [
        {"code": "cpi_yoy", "pillar": "A"},
        {"code": "credit_yoy", "pillar": "A"},
        {"code": "pmi_vn", "pillar": "B"},
    ]
    w = sc.weights(rows, CAT)
    assert w["pmi_vn"] == pytest.approx(0.5)
    assert w["cpi_yoy"] == pytest.approx(0.25)


def test_mixed_weights_fill_blank_with_mean():
    rows = [{"code": "cpi_yoy", "weight": 2}, {"code": "credit_yoy"}]  # trống → 2
    w = sc.weights(rows, CAT)
    assert w["cpi_yoy"] == pytest.approx(0.5) and w["credit_yoy"] == pytest.approx(0.5)


def test_stale_row_is_not_scored():
    card = {"rows": [CPI_ROW]}
    frames = {"cpi_yoy": monthly_frame([2.0] * 12)}  # kỳ cuối 12/2020
    table, total = sc.current(card, frames, CAT, ctx("2021-06-30"))  # quá 3 tháng
    assert bool(table.iloc[0]["stale"]) and np.isnan(table.iloc[0]["score"])
    assert np.isnan(total["score"])
    table, _ = sc.current(card, frames, CAT, ctx("2021-02-28"))  # trong 3 tháng
    assert table.iloc[0]["score"] == pytest.approx(2.0)


def test_history_carries_last_value_up_to_limit():
    card = {"rows": [CPI_ROW]}
    frames = {"cpi_yoy": monthly_frame([2.0] * 12)}  # tới 12/2020
    h = sc.history(card, frames, CAT, ctx("2021-06-30")).set_index("date")
    assert h.loc["2021-03-31", "score"] == pytest.approx(2.0)  # giữ 3 tháng
    assert np.isnan(h.loc["2021-04-30", "score"])
    assert h.index.max() == pd.Timestamp("2021-06-30")  # lưới tới tháng chấm


def test_measured_value_reported_for_transformed_row():
    card = {
        "rows": [
            {
                "code": "brent",
                "method": "absolute",
                "cuts": [-20, -5, 10, 30],
                "side": "above",
                "measure": {"kind": "pct_change", "n": 1, "unit": "year"},
            }
        ]
    }
    idx = pd.date_range("2024-01-01", "2025-06-30", freq="D")
    frame = pd.DataFrame(
        {"value": np.where(idx < "2025-01-01", 80.0, 60.0), "source": "t"}, index=idx
    )
    table, _ = sc.current(card, {"brent": frame}, CAT, ctx("2025-06-30"))
    assert table.iloc[0]["measured"] == pytest.approx(-25.0)
    assert table.iloc[0]["score"] == pytest.approx(2.0)


def test_validate_card_flags_bad_rows():
    card = {"rows": [{"code": "khong_co"}, {**CPI_ROW, "scores": [1, 0]}]}
    errors = sc.validate_card(card, CAT, SETTINGS)
    assert any("khong_co" in e for e in errors)
    assert any("2 điểm cho 5 mức" in e for e in errors)


def test_history_and_current_use_same_weights_when_a_row_has_no_data():
    """Dòng không có dữ liệu vẫn giữ trọng số: độ phủ thấp ở cả hiện tại lẫn lịch sử."""
    card = {
        "rows": [
            {**CPI_ROW, "pillar": "A"},
            {
                "code": "pmi_vn",
                "pillar": "B",
                "method": "absolute",
                "cuts": [47, 49, 51, 53],
                "side": "below",
            },
        ]
    }
    frames = {"cpi_yoy": monthly_frame([2.0] * 12)}  # PMI không có dữ liệu → độ phủ 50% < 60%
    asof = "2020-12-31"
    _, total = sc.current(card, frames, CAT, ctx(asof))
    h = sc.history(card, frames, CAT, ctx(asof)).set_index("date")
    assert total["coverage"] == pytest.approx(0.5) and np.isnan(total["score"])
    assert h.loc[asof, "coverage"] == pytest.approx(0.5) and np.isnan(h.loc[asof, "score"])


def test_history_matches_current_on_asof_month():
    card = {"rows": [CPI_ROW]}
    frames = {"cpi_yoy": monthly_frame([2.0] * 12)}
    _, total = sc.current(card, frames, CAT, ctx("2020-12-31"))
    h = sc.history(card, frames, CAT, ctx("2020-12-31")).set_index("date")
    assert h.loc["2020-12-31", "score"] == pytest.approx(total["score"])


def test_stale_bad_rows_are_flagged_in_total():
    """Dòng bị loại vì số cũ nhưng lần cuối ở mức xấu → ghi lại để cảnh báo điểm lạc quan."""
    card = {
        "rows": [
            CPI_ROW,
            {"code": "pmi_vn", "method": "absolute", "cuts": [47, 49, 51, 53], "side": "below"},
        ]
    }
    frames = {
        "cpi_yoy": monthly_frame([2.0] * 12),
        "pmi_vn": monthly_frame([40.0] * 6),
    }  # PMI cũ, mức đỏ
    _, total, _ = sc.evaluate_card(card, frames, CAT, ctx("2020-12-31"))
    assert total["n_stale"] == 1 and total["stale_bad"] == "pmi_vn"


def test_header_shows_score_even_with_stale_warning():
    from macro_app.ui import scorecard_view

    total = pd.Series(
        {
            "name": "Nhà ở",
            "score": 0.5,
            "rating": "Thuận lợi",
            "coverage": 0.9,
            "n_stale": 1,
            "stale_bad": "govbond_10y",
            "prev_score": np.nan,
        }
    )
    out = scorecard_view.header_html(total, "", {"govbond_10y": "Lợi suất TPCP 10 năm"})
    assert '<span class="sc-num">+0,50</span>' in out
    assert "Lợi suất TPCP 10 năm" in out.split('class="sc-warn"')[1]


def test_info_row_shown_but_not_scored():
    """Dòng 'chỉ tham khảo' có mức nhưng không vào trọng số, điểm, lịch sử."""
    card = {"rows": [CPI_ROW, {**CPI_ROW, "code": "pmi_vn", "info": True}]}
    frames = {"cpi_yoy": monthly_frame([2.0] * 12), "pmi_vn": monthly_frame([60.0] * 12)}
    table, total = sc.current(card, frames, CAT, ctx("2020-12-31"))
    t = table.set_index("code")
    assert t.loc["pmi_vn", "weight"] == 0 and bool(t.loc["pmi_vn", "info"])
    assert t.loc["cpi_yoy", "weight"] == pytest.approx(1.0)
    assert total["score"] == pytest.approx(2.0)
    h = sc.history(card, frames, CAT, ctx("2020-12-31")).set_index("date")
    assert h.loc["2020-12-31", "score"] == pytest.approx(2.0)
