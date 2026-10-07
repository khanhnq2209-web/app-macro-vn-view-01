"""Lớp dữ liệu VN: parser sheet wide (fixture tổng hợp) + golden trên file raw thật."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from macro_app.io import vn_raw
from macro_app.io.wide_sheet import period_to_date, to_number, wide_to_long
from macro_app.paths import RAW_DIR

REQUIRED_IDS = [
    "vn.gdp_real",
    "vn.gdp_real_realestate",
    "vn.gdp_real_construction",
    "vn.cpi_mom",
    "vn.cpi_housing_mom",
    "vn.fx_central",
    "vn.ib_on",
    "vn.refi",
    "vn.govbond_10y",
    "vn.credit_ytd",
    "vn.credit_construction_ytd",
    "vn.m2_ytd",
    "vn.public_investment",
    "vn.fdi_registered_ytd",
    "vn.target_gdp_growth",
    "vn.target_cpi_avg",
]
needs_raw = pytest.mark.skipif(
    not (RAW_DIR / "07_CPI.xlsx").exists(), reason="không có data/raw (máy khác)"
)


# ---------------------------------------------------------------- parser (tổng hợp)


def test_period_to_date_all_formats():
    labels = ["Chỉ tiêu", "03-01-2009", "02-2002", "Q1-2010", "Q4-2011", "2011", 2012, "abc"]
    got = period_to_date(labels)
    expected = [None, "2009-01-03", "2002-02-28", "2010-03-31", "2011-12-31", "2011-12-31"]
    expected += ["2012-12-31", None]
    assert list(got) == [pd.Timestamp(x) if x else pd.NaT for x in expected]


def test_to_number_comma_decimal_and_junk():
    got = to_number(pd.Series(["5,5", "1.234,5", "1,234.5", "N/A", "-", None, "7", 3]))
    assert got.tolist()[:3] == [5.5, 1234.5, 1234.5]
    assert got.iloc[3:6].isna().all()
    assert got.iloc[6] == 7.0
    assert got.iloc[7] == 3.0


def test_to_number_thousands_separator():
    got = to_number(pd.Series(["1,020.59", "147,756", "#N/A"]), thousands_sep=",")
    assert got.iloc[0] == pytest.approx(1020.59)
    assert got.iloc[1] == 147756.0
    assert np.isnan(got.iloc[2])


def _tpcp_like() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Chỉ tiêu": [
                "Đường cong lợi suất TPCP (thị trường thứ cấp)",
                "    5 năm",
                "    10 năm",
                "Lãi suất trúng thầu TPCP (thị trường sơ cấp)",
                "    10 năm",
            ],
            "02-01-2024": [None, 2.1, 2.5, None, 2.6],
            "03-01-2024": [None, "2,2", 2.4, None, None],
        }
    )


def test_wide_to_long_labels_parent_and_values():
    long = wide_to_long(_tpcp_like())
    rows = long.drop_duplicates("row_pos").set_index("row_pos")
    assert rows.loc[1, "row_label"] == "5 năm"
    assert rows.loc[2, "parent"] == "Đường cong lợi suất TPCP (thị trường thứ cấp)"
    assert rows.loc[4, "parent"] == "Lãi suất trúng thầu TPCP (thị trường sơ cấp)"
    five = long[long["row_pos"].eq(1)].set_index("date")["value"]
    assert five[pd.Timestamp("2024-01-03")] == 2.2  # chuỗi dấu phẩy thập phân


def test_wide_to_long_grouped_and_group_columns():
    grouped = pd.DataFrame(
        {
            "Chỉ tiêu (gộp cấp)": [None, "CPI bình quân - Mục tiêu"],
            "Chỉ tiêu": ["CPI bình quân", "    Mục tiêu"],
            "2025": [None, 4.5],
        }
    )
    long = wide_to_long(grouped)
    assert long["row_label"].tolist() == ["CPI bình quân", "CPI bình quân - Mục tiêu"]
    assert long["date"].iloc[1] == pd.Timestamp("2025-12-31")
    two_cols = pd.DataFrame({"Nhóm": ["Xuất"], "Chỉ tiêu": ["Tổng"], "01-2024": [100.0]})
    assert wide_to_long(two_cols)["row_label"].iloc[0] == "Xuất - Tổng"


def test_read_wide_source_picks_secondary_curve(tmp_path):
    _tpcp_like().to_excel(tmp_path / "13.xlsx", sheet_name="TPCP", index=False)
    spec = vn_raw.WideSource("13.xlsx", {"vn.govbond_10y": ("10 năm", vn_raw.GOVBOND_SECONDARY)})
    out = vn_raw.read_wide_source(spec, tmp_path).dropna(subset=["value"])
    assert out["value"].tolist() == [2.5, 2.4]
    ambiguous = vn_raw.WideSource("13.xlsx", {"x": ("10 năm", None)})
    with pytest.raises(ValueError, match="khớp 2 dòng"):
        vn_raw.read_wide_source(ambiguous, tmp_path)


def test_read_long_source_scale_and_ffill_stops_at_last_obs(tmp_path):
    frame = pd.DataFrame(
        {
            "Ngày ": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
            "   Lãi suất tái cấp vốn": [0.045, None, 0.05, None],
            "   Lãi suất BQ liên NH kỳ hạn qua đêm": [0.03, 0.031, None, 0.032],
        }
    )
    frame.to_excel(tmp_path / "06.xlsx", sheet_name="Sheet1", index=False)
    spec = vn_raw.LongSource(
        "06.xlsx",
        {"vn.refi": "Lãi suất tái cấp vốn", "vn.ib_on": "Lãi suất BQ liên NH kỳ hạn qua đêm"},
        scale=100.0,
        ffill_ids=frozenset({"vn.refi"}),
    )
    store = vn_raw.finalize_store(vn_raw.read_long_source(spec, tmp_path), "dulieukinhte")
    refi = store[store["series_id"].eq("vn.refi")].set_index("date")["value"]
    assert refi.tolist() == pytest.approx([4.5, 4.5, 5.0])  # không kéo sang 2024-01-05
    assert refi.index.max() == pd.Timestamp("2024-01-04")
    ib = store[store["series_id"].eq("vn.ib_on")]
    assert len(ib) == 3  # NaN bị bỏ


def test_finalize_store_contract_and_dedupe():
    raw = pd.DataFrame(
        {
            "series_id": ["a", "a", "b"],
            "date": [
                pd.Timestamp("2024-01-01 10:00"),
                pd.Timestamp("2024-01-01"),
                pd.Timestamp("2024-02-01"),
            ],
            "value": [1.0, 2.0, None],
        }
    )
    out = vn_raw.finalize_store(raw, "dulieukinhte")
    assert list(out.columns) == vn_raw.STORE_COLUMNS
    assert out["value"].tolist() == [2.0]  # dedupe giữ bản sau, bỏ NaN
    assert out["date"].iloc[0] == pd.Timestamp("2024-01-01")


# ---------------------------------------------------------------- golden (file raw thật)


@pytest.fixture(scope="module")
def vn_store() -> pd.DataFrame:
    return vn_raw.load_vn_series()


def _series(store: pd.DataFrame, sid: str) -> pd.Series:
    return store[store["series_id"].eq(sid)].set_index("date")["value"]


@needs_raw
def test_store_contract_and_required_ids(vn_store):
    assert list(vn_store.columns) == vn_raw.STORE_COLUMNS
    assert pd.api.types.is_datetime64_ns_dtype(vn_store["date"])
    assert vn_store["date"].dt.tz is None
    assert (vn_store["date"] == vn_store["date"].dt.normalize()).all()
    assert not vn_store.duplicated(["series_id", "date"]).any()
    assert vn_store["value"].notna().all()
    assert set(REQUIRED_IDS) <= set(vn_store["series_id"])
    assert set(vn_store["source"]) == {"dulieukinhte"}


@needs_raw
def test_golden_values(vn_store):
    fx = _series(vn_store, "vn.fx_central")
    assert fx.index.min() == pd.Timestamp("2009-01-03")
    assert fx.iloc[0] == 16973
    assert _series(vn_store, "vn.cpi_mom")[pd.Timestamp("2002-02-28")] == pytest.approx(2.2)
    assert _series(vn_store, "vn.target_cpi_avg")[pd.Timestamp("2011-12-31")] == 7
    assert _series(vn_store, "vn.target_gdp_growth")[pd.Timestamp("2012-12-31")] == 6


@needs_raw
def test_date_conventions(vn_store):
    monthly = _series(vn_store, "vn.cpi_mom").index
    assert monthly.is_month_end.all()
    quarterly = _series(vn_store, "vn.gdp_real").index
    assert quarterly.is_quarter_end.all()
    assert _series(vn_store, "vn.target_gdp_growth").index.is_year_end.all()
    assert _series(vn_store, "vn.credit_ytd").index.is_month_end.all()


@needs_raw
def test_units_are_percent(vn_store):
    refi = _series(vn_store, "vn.refi")
    assert refi.between(3, 7).all()  # 06 lưu 0.045 → đã nhân 100
    assert _series(vn_store, "vn.ib_on").median() > 0.5
    assert _series(vn_store, "vn.govbond_10y").between(1, 15).all()


@needs_raw
@pytest.mark.parametrize(
    ("file", "wide_label", "long_col"),
    [
        ("07_CPI.xlsx", "CPI", "CPI"),
        ("19_Ty-gia-trung tam USDVND.xlsx", "Trung tâm", "Trung tâm"),
    ],
)
def test_wide_sheet_matches_sheet1(file, wide_label, long_col):
    from macro_app.io.wide_sheet import read_wide_sheet

    wide = read_wide_sheet(RAW_DIR / file)
    a = wide[wide["row_label"].eq(wide_label)].set_index("date")["value"].dropna()
    b = vn_raw.read_long_sheet(RAW_DIR / file).set_index("date")[long_col].dropna()
    assert a.index.equals(b.index)
    assert np.allclose(a.to_numpy(), b.to_numpy().astype(float))


@needs_raw
def test_banks_dim():
    banks = vn_raw.load_banks()
    assert len(banks) == 20
    assert banks["is_big4"].sum() == 4
    assert set(banks.loc[banks["is_big4"], "bank_code"]) == {
        "AGRIBANK",
        "BIDV",
        "VIETCOMBANK",
        "VIETINBANK",
    }
