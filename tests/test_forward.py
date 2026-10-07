"""Dự báo ghép vào scorecard: đường lãi Fed (FedWatch), mục tiêu Chính phủ, điểm theo dự báo."""

import numpy as np
import pandas as pd
import pytest

from macro_app.config import load_catalog
from macro_app.metrics import forward as fw

CAT = {i.code: i for i in load_catalog()}


def probs(asof="2026-10-06"):
    rows = []
    for meeting, dist in {
        "2026-10-28": {(375, 400): 0.5, (400, 425): 0.5},
        "2027-04-28": {(325, 350): 0.25, (350, 375): 0.75},
        "2027-10-27": {(300, 325): 1.0},
    }.items():
        for (lo, hi), p in dist.items():
            rows.append(
                {
                    "asof": asof,
                    "meeting_date": meeting,
                    "range_low_bp": lo,
                    "range_high_bp": hi,
                    "prob": p,
                    "source": "CME QuikStrike",
                }
            )
    return pd.DataFrame(rows)


def test_fed_path_expected_rate_and_top_range():
    path = fw.fed_path(probs())
    first = path.iloc[0]
    assert first["exp_upper"] == pytest.approx(4.125)
    assert path.iloc[1]["top_range"] == "3.50–3.75%" and path.iloc[1]["top_prob"] == pytest.approx(
        0.75
    )


def test_fed_points_pick_next_year_end_12m():
    pts = fw.fed_points("fed_upper", fw.fed_path(probs()))
    # kỳ kế tiếp 10/2026 cũng là kỳ gần cuối năm nhất → gộp; +12 tháng → 10/2027
    assert [p.date.strftime("%Y-%m") for p in pts] == ["2026-10", "2027-10"]
    assert pts[-1].value == pytest.approx(3.25) and pts[-1].kind == "market"


def test_pick_prefers_cme_when_fresh_else_computed():
    cme = probs("2026-09-01")
    own = probs("2026-10-06").assign(source="Tự tính (ZQ)")
    assert (
        fw.pick_fedwatch({"quikstrike": cme, "computed": own})["source"].iloc[0] == "Tự tính (ZQ)"
    )
    assert (
        fw.pick_fedwatch({"quikstrike": probs("2026-10-05"), "computed": own})["source"].iloc[0]
        == "CME QuikStrike"
    )


def test_target_point_and_level():
    target = pd.Series([4.0, 4.5], index=pd.to_datetime(["2025-12-31", "2026-12-31"]))
    pts = fw.target_point(target, pd.Timestamp("2026-10-06"))
    assert pts[0].value == 4.5 and pts[0].label == "mục tiêu 2026"
    cfg = {"method": "absolute", "cuts": [2.5, 3.5, 4.5, 5.5], "side": "above"}
    s = pd.Series([3.0], index=[pd.Timestamp("2026-08-31")])
    assert fw.level_of(4.5, s, cfg) == "yellow"  # đúng mốc → mức tốt hơn
    assert (
        fw.level_of(4.5, s, {**cfg, "measure": {"kind": "pct_change", "n": 1, "unit": "year"}})
        is None
    )


def test_forward_total_replaces_only_rows_with_forecast():
    t = pd.DataFrame({"score": [2.0, -2.0], "weight": [0.5, 0.5], "fwd_score": [np.nan, 0.0]})
    assert fw.forward_total(t, 0.6) == pytest.approx(1.0)
    assert np.isnan(fw.forward_total(t.assign(fwd_score=np.nan), 0.6))


def test_effr_forecast_is_lower_bound_plus_8bps():
    pts = fw.fed_points("effr", fw.fed_path(probs()))
    assert pts[0].value == pytest.approx(3.875 + 0.08)  # biên dưới kỳ vọng 3,875


def test_primary_point_is_this_year_end():
    pts = fw.fed_points("fed_upper", fw.fed_path(probs()))
    assert fw.primary(pts, pd.Timestamp("2026-10-06")).date.year == 2026
    assert fw.primary([], pd.Timestamp("2026-10-06")) is None


def test_bundled_forecast_map_is_valid():
    from macro_app.config import load_targets

    maps = fw.load_forecast_map()
    assert maps
    for m in maps:
        assert fw.validate_mapping(m, CAT, set(load_targets())) == [], m
    credit = {m["code"]: m for m in maps}
    assert credit["credit_ytd"]["ref"] == "vn.target_credit_growth"  # chỉ tiêu là tăng từ đầu năm


def test_manual_and_indicator_points():
    asof = pd.Timestamp("2026-10-06")
    manual = {
        "code": "gdp_yoy_published",
        "kind": "manual",
        "value": 6.5,
        "period": "2026",
        "label": "IMF",
    }
    pts = fw.points_for(manual, path=pd.DataFrame(), targets={}, frames={}, asof=asof)
    assert (
        pts[0].value == 6.5 and pts[0].date == pd.Timestamp("2026-12-31") and pts[0].source == "IMF"
    )
    monthly = {**manual, "period": "6/2027"}
    assert fw.points_for(monthly, path=pd.DataFrame(), targets={}, frames={}, asof=asof)[
        0
    ].date == pd.Timestamp("2027-06-30")
    frame = pd.DataFrame(
        {"value": [80.0, 82.0]}, index=pd.to_datetime(["2026-10-01", "2026-10-02"])
    )
    ind = {"code": "brent", "kind": "indicator", "ref": "brent_futures", "label": "HĐ tương lai"}
    pts = fw.points_for(
        ind, path=pd.DataFrame(), targets={}, frames={"brent_futures": frame}, asof=asof
    )
    assert pts[0].value == 82.0


def test_validate_mapping_catches_bad_rows():
    bad = [
        {"code": "khong_co", "kind": "target", "ref": "vn.target_gdp_growth"},
        {"code": "effr", "kind": "fedwatch", "ref": "mid"},
        {"code": "gdp_yoy_published", "kind": "manual", "value": None, "period": ""},
        {"code": "gdp_yoy_published", "kind": "target", "ref": "vn.khong_co"},
    ]
    for m in bad:
        assert fw.validate_mapping(m, CAT, {"vn.target_gdp_growth"}), m


def test_save_forecast_map_roundtrip(tmp_path):
    from macro_app import admin

    path = tmp_path / "forecast_map.yaml"
    maps = [
        {
            "code": "gdp_yoy_published",
            "kind": "manual",
            "ref": None,
            "value": 6.5,
            "period": "2026",
            "label": "IMF",
            "note": "WEO 10/2026",
        },
        {"code": "effr", "kind": "fedwatch", "ref": "effective", "label": "FedWatch"},
    ]
    admin.save_forecast_map(maps, path)
    got = fw.load_forecast_map(path)
    assert got[0] == {
        "code": "gdp_yoy_published",
        "kind": "manual",
        "value": 6.5,
        "period": "2026",
        "label": "IMF",
        "note": "WEO 10/2026",
    }
    assert got[1]["ref"] == "effective"
    assert not list(tmp_path.glob("*.tmp"))
