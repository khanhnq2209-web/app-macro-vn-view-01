"""Gộp inbox dulieukinhte → raw: chỉ dùng workbook tổng hợp trong thư mục tạm."""

from __future__ import annotations

import pandas as pd
import pytest

from macro_app.io import inbox_merge as im

WIDE_SHEET = "CPI (Điểm)"


def _write(path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)


def _raw_wide() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Chỉ tiêu": ["CPI", "    Nhà ở và vật liệu xây dựng"],
            "01-2024": [0.1, 0.2],
            "02-2024": [0.3, None],
        }
    )


def _raw_long() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Ngày ": pd.to_datetime(["2024-01-31", "2024-02-29"]),
            "CPI": [0.1, 0.3],
            "Ghi chú": ["a", "b"],
        }
    )


@pytest.fixture
def dirs(tmp_path):
    raw, inbox, backup = tmp_path / "raw", tmp_path / "inbox", tmp_path / "raw" / "_backup"
    raw.mkdir()
    inbox.mkdir()
    _write(raw / "07_CPI.xlsx", {"Sheet1": _raw_long(), WIDE_SHEET: _raw_wide()})
    _write(raw / "other.xlsx", {"Tỷ giá USDVND": pd.DataFrame({"Chỉ tiêu": ["X"], "2024": [1]})})
    return raw, inbox, backup


def _new_wide() -> pd.DataFrame:
    # Kỳ 03-2024 mới, ô 02-2024 của CPI bị sửa lùi, ô trống được lấp, thêm 1 dòng mới
    return pd.DataFrame(
        {
            "Chỉ tiêu": ["CPI", "    Nhà ở và vật liệu xây dựng", "Lạm phát cơ bản"],
            "03-2024": [0.5, 0.6, 0.7],
            "02-2024": [0.35, 0.25, 0.8],
        }
    )


def test_wide_merge_new_wins_sorted_and_logged(dirs):
    raw, inbox, backup = dirs
    _write(inbox / "export.xlsx", {WIDE_SHEET: _new_wide()})
    reports = im.merge_inbox(inbox, raw, backup)
    sheet = reports[0]["sheets"][0]
    assert sheet["status"] == "merged"
    assert sheet["raw_file"] == "07_CPI.xlsx"
    assert (sheet["periods_added"], sheet["cells_changed"], sheet["cells_filled"]) == (1, 1, 1)
    assert sheet["rows_added"] == 1
    book = pd.read_excel(raw / "07_CPI.xlsx", sheet_name=None)
    assert list(book) == ["Sheet1", WIDE_SHEET]  # sheet khác giữ nguyên, đúng vị trí
    out = book[WIDE_SHEET]
    assert list(out.columns) == ["Chỉ tiêu", "01-2024", "02-2024", "03-2024"]
    assert out["Chỉ tiêu"].tolist()[1] == "    Nhà ở và vật liệu xây dựng"  # giữ thụt lề
    assert out["02-2024"].tolist() == [0.35, 0.25, 0.8]
    assert out["01-2024"].iloc[0] == 0.1
    assert reports[0]["moved_to"] is not None
    assert not (inbox / "export.xlsx").exists()
    assert len(list(backup.glob("*/07_CPI.xlsx"))) == 1
    log = pd.read_csv(raw / im.LOG_NAME, encoding="utf-8-sig")
    assert list(log.columns) == im.LOG_COLUMNS
    assert log["cells_changed"].tolist() == [1]


def test_rerun_same_export_is_unchanged(dirs):
    raw, inbox, backup = dirs
    _write(inbox / "a.xlsx", {WIDE_SHEET: _new_wide()})
    im.merge_inbox(inbox, raw, backup)
    _write(inbox / "b.xlsx", {WIDE_SHEET: _new_wide()})
    sheet = im.merge_inbox(inbox, raw, backup)[0]["sheets"][0]
    assert sheet["status"] == "unchanged"
    assert sheet["cells_changed"] == 0


def test_unmatched_sheet_keeps_file_in_inbox(dirs):
    raw, inbox, backup = dirs
    _write(inbox / "mix.xlsx", {WIDE_SHEET: _new_wide(), "Bảng lạ (%)": _new_wide()})
    report = im.merge_inbox(inbox, raw, backup)[0]
    statuses = {s["sheet"]: s["status"] for s in report["sheets"]}
    assert statuses == {WIDE_SHEET: "merged", "Bảng lạ (%)": "unmatched"}
    assert report["status"] == "partial"
    assert (inbox / "mix.xlsx").exists()


def test_long_sheet_upsert_by_date(dirs):
    raw, inbox, backup = dirs
    new = pd.DataFrame(
        {
            "CPI": [0.4, 0.9],
            "Ngày": pd.to_datetime(["2024-02-29", "2024-03-31"]),  # thứ tự cột khác, header strip
            "Ghi chú": ["b", "c"],
        }
    )[["Ngày", "CPI", "Ghi chú"]]
    _write(inbox / "long.xlsx", {"Bất kỳ": new})
    sheet = im.merge_inbox(inbox, raw, backup)[0]["sheets"][0]
    assert sheet["kind"] == "long"
    assert sheet["status"] == "merged"
    assert (sheet["periods_added"], sheet["cells_changed"]) == (1, 1)
    out = pd.read_excel(raw / "07_CPI.xlsx", sheet_name="Sheet1")
    assert list(out.columns) == ["Ngày ", "CPI", "Ghi chú"]
    assert out["CPI"].tolist() == [0.1, 0.4, 0.9]
    assert out["Ghi chú"].tolist() == ["a", "b", "c"]


def test_too_many_columns_is_error_not_written():
    days = pd.date_range("2000-01-01", periods=im.MAX_EXCEL_COLUMNS - 5, freq="D")
    headers = days.strftime("%d-%m-%Y")
    old = pd.DataFrame([["X", *[1.0] * len(headers)]], columns=["Chỉ tiêu", *headers])
    extra = pd.date_range(days[-1] + pd.Timedelta(days=1), periods=10, freq="D")
    new = pd.DataFrame([["X", *[2.0] * 10]], columns=["Chỉ tiêu", *extra.strftime("%d-%m-%Y")])
    with pytest.raises(ValueError, match="vượt giới hạn Excel"):
        im.merge_wide_frames(old, new)


def test_classify_sheet():
    assert im.classify_sheet(["Chỉ tiêu", "01-2024"], ["CPI"]) == "wide"
    assert im.classify_sheet(["Ngày", "CPI"], [pd.Timestamp("2024-01-31")]) == "long"
    assert im.classify_sheet(["Ngày ký", "x"], ["17/03/2014"]) == "long"
    assert im.classify_sheet(["STT", "Quyết định"], [1, 2]) is None
