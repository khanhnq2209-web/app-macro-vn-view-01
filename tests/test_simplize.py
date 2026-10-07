"""Simplize: parse API (fixture rút gọn từ response thật), upsert file 01 trên bản tạm."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from macro_app.io import simplize

FIXTURES = Path(__file__).parent / "fixtures"
TENORS = [1, 3, 6, 9, 12, 24]


class FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload, self.status_code = payload, status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise simplize.requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


class FakeSession:
    """Thay requests.Session: trả fixture theo URL, ghi lại URL đã gọi."""

    def __init__(self):
        self.calls: list[str] = []
        self.list_payload = json.loads((FIXTURES / "simplize_list.json").read_text("utf-8"))
        self.vcb = json.loads((FIXTURES / "simplize_history_VIETCOMBANK.json").read_text("utf-8"))

    def get(self, url: str, headers: dict | None = None, timeout: float = 0) -> FakeResponse:
        self.calls.append(url)
        if "/api/company/interest-rate/list" in url:
            return FakeResponse(self.list_payload)
        if url.endswith("/VIETCOMBANK"):
            return FakeResponse(self.vcb)
        agri = [
            {"ticker": "AGRIBANK", "maturity12m": 6.8, "date": 1451779200000},
            {"ticker": "AGRIBANK", "maturity12m": 6.9, "maturity36m": 7.0, "date": 1452384000000},
        ]
        return FakeResponse({"status": 200, "data": agri})


def test_history_to_panel_dates_and_tenors():
    records = FakeSession().vcb["data"]
    panel = simplize.history_to_panel(records, TENORS)
    assert panel["date"].min() == pd.Timestamp("2016-01-03")  # epoch ms 00:00 UTC
    assert set(panel["tenor_m"]) == set(TENORS)  # bỏ demand, 36m
    assert panel["rate_pct"].notna().all()
    assert pd.Timestamp("2016-03-06") not in set(panel["date"])  # bản ghi chỉ có ngày → bỏ
    first = panel[panel["date"].eq(pd.Timestamp("2016-01-03"))].set_index("tenor_m")["rate_pct"]
    assert first[12] == 6.0
    assert first[1] == 4.0


def test_fetch_simplize_panel_with_fake_session(monkeypatch):
    monkeypatch.setattr(simplize.time, "sleep", lambda _s: None)
    session = FakeSession()
    panel = simplize.fetch_simplize_panel(session=session, sleep=0)
    assert list(panel.columns) == simplize.PANEL_COLUMNS
    assert len(session.calls) == 3  # list + 2 NH
    agri = panel[panel["bank_code"].eq("AGRIBANK")]
    assert agri["tenor_m"].unique().tolist() == [12]
    assert agri["stock_code"].isna().all()
    vcb = panel[panel["bank_code"].eq("VIETCOMBANK")]
    assert set(vcb["stock_code"]) == {"VCB"}
    assert set(vcb["bank_name"]) == {"Vietcombank"}


def _file_rows(rows: list[tuple]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=simplize.FILE_COLUMNS)
    return frame.assign(ngay_du_lieu=pd.to_datetime(frame["ngay_du_lieu"]))


def test_upsert_rows_counts_added_and_changed():
    old = _file_rows(
        [
            ("2024-01-01", "VIETCOMBANK", "Vietcombank", "VCB", "12_thang", 5.0),
            ("2024-01-01", "VIETCOMBANK", "Vietcombank", "VCB", "1_thang", 2.0),
        ]
    )
    new = _file_rows(
        [
            ("2024-01-01", "VIETCOMBANK", "Vietcombank", "VCB", "12_thang", 5.2),  # đổi
            ("2024-01-01", "VIETCOMBANK", "Vietcombank", "VCB", "1_thang", 2.0),  # giữ
            ("2024-01-08", "VIETCOMBANK", "Vietcombank", "VCB", "12_thang", 5.3),  # mới
        ]
    )
    merged, stats = simplize.upsert_rows(old, new)
    assert stats == {"rows_added": 1, "rows_changed": 1}
    assert len(merged) == 3
    key = merged.set_index(["ngay_du_lieu", "ky_han"])["lai_suat_pct"]
    assert key[(pd.Timestamp("2024-01-01"), "12_thang")] == 5.2


def test_upsert_deposit_file_backup_and_preserves_sheets(tmp_path, monkeypatch):
    path = tmp_path / "01_deposit rate.xlsx"
    old = _file_rows([("2016-01-03", "VIETCOMBANK", "Vietcombank", "VCB", "12_thang", 5.5)])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        old.to_excel(writer, sheet_name=simplize.DEPOSIT_SHEET, index=False)
        pd.DataFrame({"ghi_chu": ["giữ nguyên"]}).to_excel(writer, sheet_name="Note", index=False)
    monkeypatch.setattr(simplize.time, "sleep", lambda _s: None)
    panel = simplize.fetch_simplize_panel(session=FakeSession(), sleep=0)
    stats = simplize.upsert_deposit_file(panel, path=path, backup_dir=tmp_path / "_backup")
    assert stats["written"] is True
    assert stats["rows_changed"] == 1  # 2016-01-03 VCB 12T: 5.5 → 6.0
    assert stats["rows_added"] == len(panel) - 1
    assert stats["max_date_after"] == pd.Timestamp("2026-10-06")
    assert Path(stats["backup"]).exists()
    book = pd.read_excel(path, sheet_name=None)
    assert list(book) == [simplize.DEPOSIT_SHEET, "Note"]
    out = book[simplize.DEPOSIT_SHEET]
    assert list(out.columns) == simplize.FILE_COLUMNS
    assert out["ky_han"].str.fullmatch(r"\d+_thang").all()
    assert not out.duplicated(simplize.KEY_COLUMNS).any()
    again = simplize.upsert_deposit_file(panel, path=path, backup_dir=tmp_path / "_backup")
    assert again["written"] is False  # chạy lại không đổi gì


@pytest.mark.live
def test_live_bank_list():
    session = simplize.requests.Session()
    banks = simplize.fetch_bank_list(session, simplize.simplize_config()["base_url"])
    assert len(banks) >= 15
    assert "VIETCOMBANK" in set(banks["bank_code"])
