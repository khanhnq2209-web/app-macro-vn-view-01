"""VBMA: giải mã CSV (UTF-16/tab, UTF-8/phẩy), nhãn kỳ, bảng ngân sách; HTTP giả lập."""

from __future__ import annotations

import pandas as pd
import pytest

from macro_app.io import vbma


def _utf16_tab(rows: list[list[str]]) -> bytes:
    text = "\r\n".join("\t".join(r) for r in rows)
    return text.encode("utf-16")  # có BOM FF FE như file thật


PMI_CSV = _utf16_tab([["", "1/1/2026", "1/2/2026", "1/3/2026"], ["PMI", "52.5", "N/A", "53"]])
HEATMAP_CSV = _utf16_tab(
    [
        ["-", "-", "T2 2026", "T3 2026", "T4 2026"],
        ["Chỉ số giá", "-", "-", "-", "-"],
        ["Lạm phát cơ bản", "% YoY", "3.1", "3.2", "3.3"],
        ["Lạm phát", "% YoY", "3.5", "3.6", "3.7"],
        ["Nhà ở và VLXD", "% YoY", "7.95", "8.19", "#N/A"],
        ["Chỉ số PMI", "-", "50.1", "51.0", "54.0"],
        ["Tăng trưởng GDP thực tế", "% YoY", "7.8", "7.8", "8.4"],
    ]
)
GDP_CSV = _utf16_tab(
    [
        ["", "Q1 2024", "Q2 2024", "Q1 2025", "Q2 2025"],
        ["Hoạt động kinh doanh bất động sản ", "1,000", "1,100", "1,050", "1,210"],
    ]
)
BUDGET_2024 = _utf16_tab(
    [
        ["-", "-", "3T 2024", "-", "6T 2024", "-", "9T 2024", "-", "12T 2024", "Dự toán 2024"],
        ["-", *["Thực hiện", "% thực hiện"] * 4, "-"],
        ["TỔNG THU NSNN", "1", "1", "1", "1", "1", "1", "1", "1", "1"],
        [
            "Thu tiền sử dụng đất",
            *["23,812", "27.7", "63,748", "74.2", "89,664", "104", "147,756", "172", "85,900"],
        ],
    ]
)


def test_decode_csv_utf16_tab_and_utf8_comma():
    table = vbma.decode_csv(PMI_CSV)
    assert table.iloc[1].tolist() == ["PMI", "52.5", "N/A", "53"]
    utf8 = '"Chỉ tiêu",T1 2024\nThu,"1,234"\n'.encode("utf-8-sig")
    table = vbma.decode_csv(utf8)
    assert table.iloc[1].tolist() == ["Thu", "1,234"]


def test_period_labels():
    labels = pd.Series(["T8 2026", "12T 2018", "Q1 2015", "1/5/2026", "T11 2021 ", "-", "Dự toán"])
    got = vbma.vbma_period_to_date(labels)
    expected = ["2026-08-31", "2018-12-31", "2015-03-31", "2026-05-31", "2021-11-30"]
    assert got.iloc[:5].tolist() == [pd.Timestamp(d) for d in expected]
    assert got.iloc[5:].isna().all()


def test_parse_budget_table_uses_actual_columns():
    out = vbma.parse_budget_table(vbma.decode_csv(BUDGET_2024))
    ytd = out["vbma.land_use_revenue_ytd"]
    assert ytd.tolist() == [23812, 63748, 89664, 147756]
    assert ytd.index[0] == pd.Timestamp("2024-03-31")
    assert out["vbma.land_use_revenue"].to_dict() == {pd.Timestamp("2024-12-31"): 147756}
    assert out["vbma.land_use_revenue_plan"].iloc[0] == 85900


def test_parse_heatmap_and_gdp():
    heat = vbma.parse_heatmap(vbma.decode_csv(HEATMAP_CSV))
    housing = heat["vbma.cpi_housing_yoy"]
    assert housing.tolist() == [7.95, 8.19]  # #N/A bỏ
    assert housing.index[0] == pd.Timestamp("2026-02-28")
    assert heat["vbma.gdp_yoy"].tolist() == [7.8, 7.8, 8.4]
    gdp = vbma.parse_gdp_table(vbma.decode_csv(GDP_CSV))
    assert gdp["vbma.gdp_real_realestate"].iloc[0] == 1000
    yoy = gdp["vbma.gdp_realestate_yoy"]
    assert yoy.round(6).tolist() == [5.0, 10.0]
    assert yoy.index.tolist() == [pd.Timestamp("2025-03-31"), pd.Timestamp("2025-06-30")]


class FakeResponse:
    def __init__(self, content: bytes, status: int = 200):
        self.content, self.status_code = content, status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise vbma.requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, files: dict[str, bytes]):
        self.files, self.calls = files, []

    def get(self, url: str, headers: dict | None = None, timeout: float = 0) -> FakeResponse:
        self.calls.append(url)
        path = url.removeprefix(vbma.BASE_URL + "/")
        if path in self.files:
            return FakeResponse(self.files[path])
        return FakeResponse(b"<!DOCTYPE html><html>404</html>", 404)


def test_fetch_vbma_writes_cache_and_loads_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(vbma.time, "sleep", lambda _s: None)
    files = {
        vbma.PMI_CHART: PMI_CSV,
        vbma.HEATMAP: HEATMAP_CSV,
        vbma.GDP_TABLE: GDP_CSV,
        vbma.BUDGET_TABLE.format(year=2024): BUDGET_2024,
    }
    session = FakeSession(files)
    cache = tmp_path / "vbma.xlsx"
    meta = vbma.fetch_vbma(cache, session=session, sleep=0, last_year=2025)
    assert len(session.calls) == 3 + (2025 - vbma.BUDGET_FIRST_YEAR + 1)
    assert set(meta.loc[meta["status"].eq("ok"), "series_id"]) >= {
        "vbma.pmi",
        "vbma.land_use_revenue",
        "vbma.cpi_housing_yoy",
        "vbma.gdp_realestate_yoy",
    }
    store = vbma.load_vbma_series(cache)
    assert list(store.columns) == ["series_id", "date", "value", "source"]
    assert set(store["source"]) == {"VBMA"}
    pmi = store[store["series_id"].eq("vbma.pmi")].set_index("date")["value"]
    # chart: T1=52.5, T3=53 (T2 N/A); heatmap bổ sung T2=50.1 và T4=54.0; T3 giữ số chart
    assert pmi.to_dict() == {
        pd.Timestamp("2026-01-31"): 52.5,
        pd.Timestamp("2026-02-28"): 50.1,
        pd.Timestamp("2026-03-31"): 53.0,
        pd.Timestamp("2026-04-30"): 54.0,
    }


def test_fetch_vbma_failure_keeps_previous_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(vbma.time, "sleep", lambda _s: None)
    cache = tmp_path / "vbma.xlsx"
    full = {vbma.PMI_CHART: PMI_CSV, vbma.HEATMAP: HEATMAP_CSV, vbma.GDP_TABLE: GDP_CSV}
    full[vbma.BUDGET_TABLE.format(year=2024)] = BUDGET_2024
    vbma.fetch_vbma(cache, session=FakeSession(full), sleep=0, last_year=2024)
    partial = {k: v for k, v in full.items() if "thu_chi" not in k}
    meta = vbma.fetch_vbma(cache, session=FakeSession(partial), sleep=0, last_year=2024)
    store = vbma.load_vbma_series(cache)
    assert "vbma.land_use_revenue" in set(store["series_id"])  # giữ bản cũ
    row = meta.set_index("series_id").loc["vbma.land_use_revenue"]
    assert "không tải được" in row["error"]


@pytest.mark.live
def test_live_pmi_chart():
    import requests

    table = vbma.fetch_csv(requests.Session(), vbma.PMI_CHART)
    assert table is not None
    pmi = vbma.parse_pmi_chart(table)
    assert pmi.between(30, 70).all()
    assert pmi.index.max() >= pd.Timestamp("2026-01-31")


def test_budget_year_identical_to_previous_is_dropped():
    first = vbma.decode_csv(BUDGET_2024)
    copied = first.replace(r"2024", "2025", regex=True)  # bảng năm sau chép y hệt số
    out = vbma.parse_budget_tables([first, copied])
    assert out["vbma.land_use_revenue"].index.year.tolist() == [2024]
