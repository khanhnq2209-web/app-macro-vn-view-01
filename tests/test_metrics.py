"""Golden tests cho metrics thuần (dữ liệu tổng hợp, không đọc data/)."""

import numpy as np
import pandas as pd
import pytest

from macro_app.config import load_catalog, load_impact_rules, load_thresholds
from macro_app.metrics import impact as imp
from macro_app.metrics import transforms as tf
from macro_app.metrics.recipes import RawContext, compute_all
from macro_app.metrics.status import RED, YELLOW, evaluate, resolve_threshold


def monthly(values, start="2020-01-31"):
    return pd.Series(
        values, index=pd.date_range(start, periods=len(values), freq="ME"), dtype=float
    )


def test_mom_to_yoy_constant_1pct_per_month():
    s = monthly([1.0] * 24)
    yoy = tf.mom_to_yoy(s).dropna()
    assert len(yoy) == 12
    assert yoy.iloc[-1] == pytest.approx((1.01**12 - 1) * 100)


def test_mom_to_yoy_gap_breaks_chain():
    s = monthly([0.5] * 30).drop(pd.Timestamp("2021-03-31"))
    yoy = tf.mom_to_yoy(s)
    assert yoy.loc["2021-03-31":].isna().all()


def test_cpi_avg_ytd_equals_yoy_when_inflation_constant():
    s = monthly([0.2] * 36)
    avg = tf.mom_to_avg_ytd(s).dropna()
    yoy = tf.mom_to_yoy(s).dropna()
    assert avg.iloc[-1] == pytest.approx(yoy.iloc[-1])


def test_yoy_pct_quarterly():
    q = pd.Series(
        [100, 101, 102, 103, 110], index=pd.date_range("2020-03-31", periods=5, freq="QE")
    )
    assert tf.yoy_pct(q, "Q").iloc[-1] == pytest.approx(10.0)


def test_ytd_change_pct_daily():
    idx = pd.to_datetime(["2025-12-30", "2025-12-31", "2026-01-02", "2026-03-02"])
    s = pd.Series([24000, 25000, 25100, 25500], index=idx)
    assert tf.ytd_change_pct(s).iloc[-1] == pytest.approx(2.0)


def test_ytd_sum_yoy():
    s = monthly([10] * 12 + [12] * 3, start="2025-01-31")
    assert tf.ytd_sum_yoy(s).iloc[-1] == pytest.approx(20.0)


def test_extend_appends_only_newer_dates():
    p = pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-01-01", "2026-01-02"]))
    s = pd.Series([9.0, 3.0], index=pd.to_datetime(["2026-01-02", "2026-01-03"]))
    out = tf.extend(p, s)
    assert out.tolist() == [1.0, 2.0, 3.0]


def test_change_units():
    assert tf.change(4.25, 4.0, "bps") == pytest.approx(25.0)
    assert tf.change(4.25, 4.0, "pp") == pytest.approx(0.25)
    assert tf.change(110, 100, "pct") == pytest.approx(10.0)


def test_zscore_needs_min_points():
    s = monthly(list(range(10)))
    assert np.isnan(tf.zscore_latest(s, 5, 24))


def test_status_zscore_red_and_side():
    s = monthly([0.0, 1.0] * 15 + [10.0])
    cfg = {
        "method": "zscore",
        "yellow": 1.0,
        "red": 2.0,
        "side": "both",
        "window_years": 5,
        "min_points": {"M": 24},
    }
    assert evaluate(s, "M", cfg, "default").status == RED
    low = monthly([0.0, 1.0] * 15 + [-10.0])
    assert evaluate(low, "M", {**cfg, "side": "above"}, "x").status == "green"


def test_status_target_band():
    s = monthly([3.5, 4.6])
    cfg = {"method": "target_band", "yellow": 0.5, "red": 1.0, "side": "above"}
    assert evaluate(s, "M", cfg, "f", target_value=4.0).status == YELLOW


def test_status_absolute_ranges():
    s = monthly([5.5])
    cfg = {"method": "absolute", "green": [[None, 4.0]], "yellow": [[4.0, 5.0]]}
    assert evaluate(s, "M", cfg, "f").status == RED


def test_resolve_threshold_absolute_does_not_inherit_numeric_yellow():
    default, _ = load_thresholds()
    cfg, src = resolve_threshold(
        "x", default, {"x": {"method": "absolute", "green": [[0, 1]], "_file": "a"}}
    )
    assert "yellow" not in cfg and src == "a"


def test_trend_and_favorability():
    params = {"lookback_periods": {"M": 3}, "flat_std_ratio": 0.25}
    rising = monthly([1, 1.1, 0.9, 1.0, 1.05, 0.95, 1.0, 2.0])
    direction, _ = imp.trend(rising, "M", params)
    assert direction == imp.UP
    assert imp.favorability("up_bad", imp.UP) == imp.UNFAVORABLE
    assert imp.favorability("up_good", imp.UP) == imp.FAVORABLE
    assert imp.favorability("two_way", imp.DOWN) == imp.TWO_WAY


def test_group_cells_flip_and_keep_both():
    rules = load_impact_rules()["groups"]
    assert imp.group_cells(rules["B3"], imp.DOWN)["housing_demand"] == "up"  # LS giảm → cầu nhà ở ↑
    assert imp.group_cells(rules["B4"], imp.DOWN)["housing_demand"] == "both"
    assert imp.group_cells(rules["A4"], imp.DOWN)["industrial_demand"] == "up"  # khi = giảm
    assert imp.group_cells(rules["D2"], imp.UP)["housing_demand"] == "up"
    assert imp.group_cells(rules["E1"], imp.UP)["industrial_demand"] == "up"


def test_catalog_loads_and_representatives_unique():
    cat = load_catalog()
    reps = [i.group for i in cat if i.representative]
    assert len(reps) == len(set(reps))
    groups = load_impact_rules()["groups"]
    assert {i.group for i in cat} <= set(groups)


def test_compute_all_diff_uses_month_end():
    cat = [i for i in load_catalog() if i.code in ("credit_ytd", "m2_ytd", "credit_minus_m2")]
    store = pd.concat(
        [
            pd.DataFrame(
                {
                    "series_id": "vn.credit_ytd",
                    "date": monthly([5.0, 6.0]).index,
                    "value": [5.0, 6.0],
                    "source": "dulieukinhte",
                }
            ),
            pd.DataFrame(
                {
                    "series_id": "vn.m2_ytd",
                    "date": monthly([4.0, 4.5]).index,
                    "value": [4.0, 4.5],
                    "source": "dulieukinhte",
                }
            ),
        ]
    )
    frames = compute_all(cat, RawContext(store=store))
    assert frames["credit_minus_m2"]["value"].tolist() == pytest.approx([1.0, 1.5])


def test_quarter_end_values_drops_incomplete_quarter():
    s = monthly([5.0, 5.0, 5.0, 6.0, 6.0, 6.0, 6.0, 6.0], start="2026-01-31")  # T7, T8 lặp Q2
    out = tf.quarter_end_values(s)
    assert list(out.index.strftime("%Y-%m-%d")) == ["2026-03-31", "2026-06-30"]


def test_refresh_status_reports_series_errors():
    from macro_app.admin import _status_from_meta

    meta = pd.DataFrame({"status": ["ok", "error", "error"]})
    assert _status_from_meta(meta).startswith("lỗi 2/3")
    assert _status_from_meta(pd.DataFrame({"status": ["ok"]})) == "ok"
    assert _status_from_meta({"rows_added": 5}) == "ok"


def test_trend_vs_last_year_ignores_january_reset():
    from macro_app.metrics.impact import trend_vs_last_year

    params = {"lookback_periods": {"M": 3}, "flat_std_ratio": 0.25}
    ytd = monthly([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] * 3 + [1.5], start="2023-01-31")
    direction, delta = trend_vs_last_year(ytd, "M", params)
    assert direction == "up" and delta == pytest.approx(0.5)  # T1 năm nay 1,5 > T1 năm trước 1,0


def test_save_threshold_accepts_numpy_and_rejects_bad_order(tmp_path, monkeypatch):
    import yaml

    from macro_app import admin

    monkeypatch.setattr(admin, "THRESHOLD_HISTORY_FILE", tmp_path / "h.csv")
    path = tmp_path / "90_ui.yaml"
    cfg = {
        "method": "zscore",
        "window_years": np.int64(5),
        "cuts": [np.float64(1.5), np.float64(2.5)],
        "side": "both",
        "description": "thử",
        "green": np.nan,
    }
    admin.save_threshold("x", cfg, {"method": "zscore"}, "u", path=path)
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))["x"]
    assert saved == {
        "method": "zscore",
        "window_years": 5,
        "cuts": [1.5, 2.5],
        "side": "both",
        "description": "thử",
    }
    with pytest.raises(ValueError):
        admin.save_threshold("x", {"method": "zscore", "cuts": [3.0, 2.0]}, {}, "u", path=path)


def test_status_levels_and_methods():
    from macro_app.metrics.status import evaluate, validate_cfg

    base = monthly([float(i % 10) for i in range(60)] + [9.5])  # 5 năm, giá trị cuối cao
    mp = {"M": 24}
    # ngưỡng cứng, cao là xấu, 4 mức
    cfg = {"method": "absolute", "cuts": [3.0, 6.0, 9.0], "side": "above"}
    assert evaluate(base, "M", cfg, "f").status == "red"
    assert evaluate(monthly([5.0]), "M", cfg, "f").status == "yellow"
    # ngưỡng cứng, thấp là xấu, 5 mức (GDP dưới 5% là đỏ)
    cfg = {"method": "absolute", "cuts": [5.0, 6.0, 7.0, 8.0], "side": "below"}
    assert evaluate(monthly([4.5]), "M", cfg, "f").status == "red"
    assert evaluate(monthly([8.4]), "M", cfg, "f").status == "green_strong"
    # phân vị một phía: phân vị ~ cao → đỏ
    cfg = {
        "method": "percentile",
        "window_years": 5,
        "cuts": [50, 75, 90],
        "side": "above",
        "min_points": mp,
    }
    assert evaluate(base, "M", cfg, "f").status == "red"
    # phân vị hai phía: mốc là khoảng cách tới P50
    cfg = {
        "method": "percentile",
        "window_years": 5,
        "cuts": [25, 40],
        "side": "both",
        "min_points": mp,
    }
    mid = monthly([float(i % 10) for i in range(60)] + [4.5])
    assert evaluate(mid, "M", cfg, "f").status == "green"
    # z-score thấp là xấu: z dương không bị coi là xấu
    cfg = {
        "method": "zscore",
        "window_years": 5,
        "cuts": [1.0, 2.0],
        "side": "below",
        "min_points": mp,
    }
    assert evaluate(base, "M", cfg, "f").status == "green"
    # lệch median
    cfg = {
        "method": "median_dev",
        "window_years": 5,
        "cuts": [2.0, 4.0],
        "side": "above",
        "min_points": mp,
    }
    assert evaluate(base, "M", cfg, "f").status == "red"  # 9,5 − median 4,5 = 5 > 4
    # kiểm tra cấu hình
    assert validate_cfg({"method": "absolute", "cuts": [1.0], "side": "above"})
    assert validate_cfg(
        {"method": "absolute", "cuts": [1.0, 2.0, 3.0], "side": "both"}
    )  # hai phía cần số mốc chẵn
    assert validate_cfg(
        {"method": "percentile", "window_years": 5, "cuts": [10.0, 60.0], "side": "both"}
    )
    assert not validate_cfg(
        {"method": "percentile", "window_years": 5, "cuts": [25.0, 40.0], "side": "both"}
    )


def test_threshold_editor_parse_cuts():
    from macro_app.ui.threshold_editor import cuts_text, parse_cuts

    assert parse_cuts("3,5; 4; 4,5") == [3.5, 4.0, 4.5]
    assert parse_cuts("0.5;1") == [0.5, 1.0]
    assert parse_cuts("") is None
    assert cuts_text([3.5, 4.0, 25.0]) == "3,5; 4; 25"


def test_fedwatch_summary_uses_range_in_force_each_day():
    from macro_app.metrics.fedwatch_table import summary

    df = pd.DataFrame(
        {
            "asof": pd.to_datetime(["2026-09-10", "2026-09-10", "2026-09-20", "2026-09-20"]),
            "meeting_date": pd.to_datetime(["2026-10-28"] * 4),
            "range_low_bp": [350, 375, 375, 400],
            "range_high_bp": [375, 400, 400, 425],
            "prob": [0.6, 0.4, 0.7, 0.3],
        }
    )
    ranges = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-07-01", "2026-09-17"]),
            "low_bp": [350, 375],
            "high_bp": [375, 400],
        }
    )
    out = summary(df, ranges).set_index("asof")
    assert out.loc["2026-09-10", "hold"] == pytest.approx(
        0.6
    )  # trước đợt tăng 17/9: 350–375 là giữ
    assert out.loc["2026-09-20", "hold"] == pytest.approx(0.7)
    assert out.loc["2026-09-20", "cut"] == 0


def test_public_files_have_no_yahoo_values():
    from macro_app.paths import PUBLIC_DIR

    if not (PUBLIC_DIR / "latest.csv").exists():
        pytest.skip("chưa build")
    latest = pd.read_csv(PUBLIC_DIR / "latest.csv")
    yahoo = latest[latest["row_source"] == "Yahoo"]
    assert yahoo["value"].isna().all() and yahoo["zscore_5y"].isna().all()
    hist = pd.read_csv(PUBLIC_DIR / "status_history.csv")
    assert hist[hist["code"].isin(yahoo["code"])]["value"].isna().all()
    for f in (PUBLIC_DIR / "series").glob("*.csv"):
        assert "Yahoo" not in set(pd.read_csv(f)["source"].astype(str)), f.name


def test_impact_sign_flips_inverse_indicators():
    rules = load_impact_rules()["groups"]
    # spread HY tăng = tăng trưởng toàn cầu yếu đi → cầu nhà ở theo quy tắc A5 phải đảo thành giảm
    assert imp.group_cells(rules["A5"], imp.apply_sign(imp.UP, -1))["housing_demand"] == "down"
    assert imp.apply_sign(imp.FLAT, -1) == imp.FLAT


def test_published_yoy_preferred_over_mom_chain():
    cat = [i for i in load_catalog() if i.code == "cpi_yoy"]
    idx = monthly([0.0] * 26, start="2022-01-31").index
    mom = [0.1] * 11 + [4.55] + [0.1] * 14  # T12/2022 nhập nhầm
    store = pd.concat(
        [
            pd.DataFrame(
                {"series_id": "vn.cpi_mom", "date": idx, "value": mom, "source": "dulieukinhte"}
            ),
            pd.DataFrame(
                {"series_id": "vbma.cpi_yoy", "date": idx[12:], "value": 4.0, "source": "VBMA"}
            ),
        ]
    )
    out = compute_all(cat, RawContext(store=store))["cpi_yoy"]
    assert out.loc["2023-06-30", "value"] == pytest.approx(
        4.0
    )  # lấy số công bố, không lấy chuỗi lỗi
    assert out.loc["2023-06-30", "source"] == "VBMA"


def test_ytd_to_yoy_matches_level_based_yoy():
    level = pd.Series(
        range(100, 136), index=pd.date_range("2023-01-31", periods=36, freq="ME"), dtype=float
    )
    dec = level[level.index.month == 12]
    base = pd.Series(level.index.year - 1, index=level.index).map(
        pd.Series(dec.to_numpy(), index=dec.index.year)
    )
    ytd = (level / base - 1) * 100
    expected = (level / level.shift(12) - 1) * 100
    got = tf.ytd_to_yoy(ytd)
    assert got.loc["2025-06-30"] == pytest.approx(expected.loc["2025-06-30"])


def test_repeat_flag():
    from macro_app.metrics.quality import has_repeat

    assert has_repeat(monthly([1.0, 2.0, 3.18, 3.18, 4.0]), "M")
    assert not has_repeat(monthly([1.0, 2.0, 3.0]), "M")


def test_status_middle_is_bad():
    from macro_app.metrics.status import evaluate

    mp = {"M": 24}
    hist = [float(i % 10) for i in range(60)]
    cfg = {
        "method": "percentile",
        "window_years": 5,
        "cuts": [10, 30],
        "side": "middle",
        "min_points": mp,
    }
    assert evaluate(monthly([*hist, 4.5]), "M", cfg, "f").status == "red"  # sát P50
    assert evaluate(monthly([*hist, 9.9]), "M", cfg, "f").status == "green"  # ở đầu phân phối
    cfg = {
        "method": "zscore",
        "window_years": 5,
        "cuts": [0.5, 1.0],
        "side": "middle",
        "min_points": mp,
    }
    assert evaluate(monthly([*hist, 4.5]), "M", cfg, "f").status == "red"


def test_threshold_preview_bands_and_shares():
    from macro_app.metrics import threshold_preview as tp

    s = monthly([float(i % 10) for i in range(60)] + [9.5])
    cfg = {"method": "absolute", "cuts": [3.0, 6.0, 9.0], "side": "above"}
    assert tp.boundaries(s, cfg, np.nan) == [3.0, 6.0, 9.0]
    bands = tp.bands(s, cfg, np.nan, 0.0, 10.0)
    assert [b[2] for b in bands] == ["green", "yellow", "orange", "red"]
    shares = tp.level_shares(tp.history_scores(s, cfg, "M", None), cfg)
    assert sum(shares.values()) == pytest.approx(100, abs=2)
    # z-score hai phía: ranh giới đối xứng quanh trung bình
    cfg = {
        "method": "zscore",
        "window_years": 5,
        "cuts": [1.0, 2.0],
        "side": "both",
        "min_points": {"M": 24},
    }
    b = tp.boundaries(s, cfg, np.nan)
    mean = s[s.index > s.index[-1] - pd.DateOffset(years=5)].mean()
    assert len(b) == 4 and b[0] + b[3] == pytest.approx(2 * mean)
    assert tp.status_of_score(tp.score_fn(s, cfg, np.nan)(mean), cfg) == "green"
    assert len(tp.suggest_cuts(s, "percentile", "above", 3, 5)) == 3
