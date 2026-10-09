"""Golden tests scorecard: trọng số, điểm tổng, thiếu dữ liệu, lịch sử không nhìn trước."""

import numpy as np
import pandas as pd
import pytest

from macro_app.config import load_catalog, load_thresholds
from macro_app.metrics import scorecard as sc

CAT = {i.code: i for i in load_catalog()}
SETTINGS = sc.load_settings()
CPI_ROW_BASE = {
    "code": "cpi_yoy",
    "method": "absolute",
    "cuts": [2.5, 3.5, 4.5, 5.5],
    "side": "above",
}


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


def test_row_weights_inside_pillar_keep_entered_and_split_rest():
    rows = [
        {"code": "cpi_yoy", "pillar": "A", "weight": 60},
        {"code": "credit_yoy", "pillar": "A"},
        {"code": "pmi_vn", "pillar": "A"},
    ]
    w = sc.weights(rows, CAT)
    assert w["cpi_yoy"] == pytest.approx(0.6)
    assert w["credit_yoy"] == pytest.approx(0.2) and w["pmi_vn"] == pytest.approx(0.2)


def test_pillar_weights_keep_entered_and_split_rest():
    rows = [
        {"code": "cpi_yoy", "pillar": "A"},
        {"code": "credit_yoy", "pillar": "B"},
        {"code": "pmi_vn", "pillar": "C"},
    ]
    w = sc.weights(rows, CAT, [{"name": "A", "weight": 70}])
    assert w == pytest.approx({"cpi_yoy": 0.7, "credit_yoy": 0.15, "pmi_vn": 0.15})


def test_bad_weights_are_flagged_and_still_sum_to_one():
    card = {
        "pillars": [{"name": "A", "weight": 80}, {"name": "B", "weight": 40}],
        "rows": [
            {**CPI_ROW_BASE, "pillar": "A"},
            {**CPI_ROW_BASE, "code": "pmi_vn", "pillar": "B"},
        ],
    }
    w = sc.weights(card["rows"], CAT, card["pillars"])
    assert sum(w.values()) == pytest.approx(1.0) and w["cpi_yoy"] == pytest.approx(80 / 120)
    assert any("vượt 100%" in e for e in sc.validate_card(card, CAT, SETTINGS))
    card["pillars"] = [{"name": "A", "weight": 50}, {"name": "B", "weight": 30}]
    assert any("cần đủ 100%" in e for e in sc.validate_card(card, CAT, SETTINGS))
    card["pillars"].append({"name": "Trống", "weight": None})
    assert any("Trống chưa có chỉ số" in e for e in sc.validate_card(card, CAT, SETTINGS))


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


def test_hero_cards_show_score_stale_rows_and_sensitivity():
    from macro_app.ui import scorecard_view

    card = {
        "rows": [
            {**CPI_ROW, "pillar": "A"},
            {**CPI_ROW, "code": "pmi_vn", "pillar": "B", "cuts": [47, 49, 51, 53], "side": "below"},
        ]
    }
    frames = {"cpi_yoy": monthly_frame([2.0] * 12), "pmi_vn": monthly_frame([40.0] * 6)}
    table, total, _ = sc.evaluate_card(card, frames, CAT, ctx("2020-12-31"))
    out = scorecard_view.score_html({**total, "score": 2.0, "rating": "Rất thuận lợi"}, {}, "x")
    assert '<span class="sc3-num">+2,00</span>' in out
    names = {"pmi_vn": "PMI"}
    trust = scorecard_view.trust_html(total, table, names, pd.DataFrame(), SETTINGS["rating_bands"])
    assert "PMI · Rất xấu" in trust  # chỉ số số cũ kèm mức cuối đã biết
    assert "Nếu số cũ quay lại" in trust and "có thể đổi xếp hạng" in trust


def test_gauge_needle_and_labels():
    from macro_app.ui import scorecard_view

    fig = scorecard_view.gauge_figure(0.32, SETTINGS["rating_bands"])
    texts = [a.text for a in fig.layout.annotations]
    assert "≤ −1" in texts and "≥ 1,2" in texts and "0,05" in texts
    assert sum(sh.type == "path" for sh in fig.layout.shapes) == 6  # 5 dải + kim
    empty = scorecard_view.gauge_figure(float("nan"), SETTINGS["rating_bands"])
    assert sum(sh.type == "path" for sh in empty.layout.shapes) == 5  # chưa có điểm: không vẽ kim


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


def test_contributions_add_up_to_score_when_a_row_is_stale():
    """Đóng góp hiển thị đã chia độ phủ: cộng lại đúng bằng điểm tổng (lỗi cũ: +0,23 ≠ +0,32)."""
    card = {
        "rows": [
            {**CPI_ROW, "pillar": "A"},
            {**CPI_ROW, "code": "pmi_vn", "pillar": "A", "cuts": [47, 49, 51, 53], "side": "below"},
            {
                **CPI_ROW,
                "code": "credit_yoy",
                "pillar": "B",
                "cuts": [8, 11, 15, 18],
                "side": "below",
            },
        ]
    }
    frames = {
        "cpi_yoy": monthly_frame([4.0] * 12),  # Trung tính 0
        "pmi_vn": monthly_frame([40.0] * 6),  # số cũ: không tính
        "credit_yoy": monthly_frame([16.0] * 12),  # Tốt +1
    }
    table, total = sc.current(card, frames, CAT, ctx("2020-12-31"))
    assert total["coverage"] == pytest.approx(0.75)
    assert total["score"] == pytest.approx(0.5 / 0.75)
    assert table["contribution"].sum() == pytest.approx(total["score"])
    t = table.set_index("code")
    assert t.loc["credit_yoy", "weight_used"] == pytest.approx(0.5 / 0.75)
    assert np.isnan(t.loc["pmi_vn", "contribution"]) and t.loc["pmi_vn", "weight_used"] == 0


def test_measured_unit_follows_measure():
    from macro_app.metrics.summary import measure_unit

    assert measure_unit(None, "%") == "%"
    assert measure_unit({"kind": "change", "n": 1, "unit": "year"}, "%") == "điểm %"
    assert measure_unit({"kind": "pct_change", "n": 1, "unit": "year"}, "điểm") == "%"
    assert (
        measure_unit({"kind": "mean", "n": 21, "unit": "day"}, "điểm") == "điểm"
    )  # VIX không phải %
    card = {
        "rows": [
            {
                **CPI_ROW,
                "code": "govbond_10y",
                "measure": {"kind": "change", "n": 1, "unit": "year"},
            }
        ]
    }
    table, _ = sc.current(card, {"govbond_10y": monthly_frame([3.0] * 13)}, CAT, ctx("2021-01-31"))
    assert table.iloc[0]["measured_unit"] == "điểm %"


def test_sensitivity_of_stale_rows():
    card = {
        "rows": [
            {**CPI_ROW, "pillar": "A"},
            {**CPI_ROW, "code": "pmi_vn", "pillar": "B", "cuts": [47, 49, 51, 53], "side": "below"},
        ]
    }
    frames = {"cpi_yoy": monthly_frame([2.0] * 12), "pmi_vn": monthly_frame([40.0] * 6)}
    table, _ = sc.current(card, frames, CAT, ctx("2020-12-31"))
    sens = sc.sensitivity(table)
    assert sens["codes"] == ["pmi_vn"] and sens["weight"] == pytest.approx(0.5)
    assert sens["keep"] == pytest.approx((2 * 0.5 + -2 * 0.5) / 1.0)  # PMI giữ mức cuối Rất xấu
    assert sens["worst"] == pytest.approx(0.0) and sens["best"] == pytest.approx(2.0)


def test_compare_previous_month_explains_change_by_pillar():
    card = {
        "rows": [
            {**CPI_ROW, "pillar": "A"},
            {
                **CPI_ROW,
                "code": "credit_yoy",
                "pillar": "B",
                "cuts": [8, 11, 15, 18],
                "side": "below",
            },
        ]
    }
    frames = {
        "cpi_yoy": monthly_frame([2.0] * 11 + [6.0]),  # tháng 12 xấu đi: +2 → −2
        "credit_yoy": monthly_frame([16.0] * 12),
    }
    _, total, _ = sc.evaluate_card(card, frames, CAT, ctx("2020-12-31"))
    prev = total["compare"][1]
    assert prev["date"] == pd.Timestamp("2020-11-30")
    assert prev["total"] == pytest.approx(total["prev_score"])
    assert prev["rows"]["cpi_yoy"] == pytest.approx(2.0)
    pill = {p["pillar"]: p for p in total["pillars"]}
    diff = sum(pill[k]["contribution"] - prev["pillars"].get(k, 0) for k in pill)
    assert diff == pytest.approx(
        total["score"] - prev["total"]
    )  # chênh từng nhóm cộng ra chênh điểm
    assert pill["A"]["level"] == -2 and pill["B"]["level"] == 1


def test_bundled_profile_scores_match_last_build():
    """Golden: đổi cách chia tỷ trọng không làm lệch điểm bộ đang dùng (chưa nhập tỷ trọng nào)."""
    import json

    from macro_app import profiles
    from macro_app.paths import APP_DIR
    from macro_app.ui import data

    totals_path = APP_DIR / "scorecard_totals.parquet"
    if not totals_path.exists():
        pytest.skip("chưa build")
    built = pd.read_parquet(totals_path).set_index(["profile", "segment"])
    asof = pd.Timestamp(
        json.loads((APP_DIR / "build_meta.json").read_text(encoding="utf-8"))["built_at"][:10]
    )
    frames, targets = data._scorecard_inputs.__wrapped__(data.build_stamp())
    c = sc.make_context(
        frames,
        CAT,
        targets,
        asof=asof,
        settings=SETTINGS,
        min_points=load_thresholds()[0]["min_points"],
    )
    checked = 0
    for pslug, prof in profiles.load_profiles().items():
        if pslug != "theo_doi_bds_01":  # bộ gốc, chưa nhập tỷ trọng; bộ khác có thể sửa sau build
            continue
        for slug, card in prof["segments"].items():
            if (pslug, slug) not in built.index:
                continue
            _, total = sc.current(card, frames, CAT, c)
            assert total["score"] == pytest.approx(built.loc[(pslug, slug), "score"], nan_ok=True)
            checked += 1
    assert checked >= 2


def test_reference_cell_labels_market_and_target():
    from macro_app.ui import scorecard_view

    lat = pd.Series({"unit": "%"})
    rec = pd.Series({"fwd_value": 4.07, "fwd_kind": "market", "fwd_source": "FedWatch"})
    assert "Kỳ vọng" in scorecard_view._ref_cell(rec, lat, 2)
    rec = pd.Series({"fwd_value": 15.0, "fwd_kind": "target"})
    assert "15%" in scorecard_view._ref_cell(
        rec, lat, 2
    ) and "Mục tiêu" in scorecard_view._ref_cell(rec, lat, 2)
    out = scorecard_view._ref_cell(rec, pd.Series({"unit": "tỷ đồng"}), 0)
    assert "Kế hoạch" in out


def test_blank_weights_that_would_become_zero_are_flagged():
    card = {
        "pillars": [{"name": "A", "weight": 100}, {"name": "B"}],
        "rows": [{**CPI_ROW, "pillar": "A"}, {**CPI_ROW, "code": "pmi_vn", "pillar": "B"}],
    }
    assert any("sẽ thành 0%" in e for e in sc.weight_errors(card, CAT))


def test_pillar_level_rounds_half_up():
    table = pd.DataFrame(
        {
            "code": ["a", "b"],
            "pillar": ["P", "P"],
            "info": [False, False],
            "score": [1.0, 0.0],
            "weight": [0.5, 0.5],
            "contribution": [0.5, 0.0],
        }
    )
    assert sc.pillar_table(table, ["P"]).iloc[0]["level"] == 1  # trung bình 0,5 → 1, không về 0


def test_rating_below_lowest_band_does_not_crash():
    assert sc.rating(-150.0, SETTINGS["rating_bands"]) == SETTINGS["rating_bands"][-1]["label"]


def test_level_scores_outside_range_are_flagged():
    card = {"rows": [{**CPI_ROW, "scores": [20, 1, 0, -1, -2]}]}
    assert any("−2 đến +2" in e for e in sc.validate_card(card, CAT, SETTINGS))


def test_distance_to_worse_level_uses_same_tie_rule_as_scoring():
    """Đúng bằng mốc thuộc mức tốt hơn → khoảng cách tới mức xấu hơn là 0."""
    from macro_app.ui import scorecard_view

    row = {"method": "absolute", "side": "above", "cuts": [0.0, 1.0, 4.0, 6.0]}
    assert scorecard_view.next_worse(row, 4.0, "yellow", "%") == "cách mức Xấu: 0,00 điểm %"
    assert scorecard_view.next_worse(row, 3.5, "yellow", "%") == "cách mức Xấu: 0,50 điểm %"
    below = {"method": "absolute", "side": "below", "cuts": [5.0, 6.0, 7.0, 8.0]}
    assert scorecard_view.next_worse(below, 7.0, "green", "%") == "cách mức Trung tính: 0,00 điểm %"


def test_markdown_escape_blocks_links_but_keeps_dashes():
    from macro_app import fmt

    assert fmt.md("Theo dõi BĐS - 01") == "Theo dõi BĐS - 01"
    assert "](" not in fmt.md("[bấm](http://x)") and "![" not in fmt.md("![a](b)")
