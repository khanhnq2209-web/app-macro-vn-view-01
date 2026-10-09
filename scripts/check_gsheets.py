"""Kiểm tra kết nối Google Sheets của kho cấu hình scorecard. Chỉ ĐỌC; không in khóa hay nội dung.

Chạy:  python scripts/check_gsheets.py
Đọc mục [gsheets] trong .streamlit/secrets.toml. Cần:  pip install gspread
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

SECRETS = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"
HEADERS = [
    "bo_id",
    "version",
    "status",
    "payload",
    "saved_by",
    "saved_at",
    "approved_by",
    "approved_at",
]
REQUIRED = ("spreadsheet", "type", "project_id", "private_key", "client_email")
HINTS = {
    "SpreadsheetNotFound": "Sai URL, hoặc chưa chia sẻ Sheet cho client_email (quyền Editor).",
    "WorksheetNotFound": "Sheet chưa có tab tên đúng 'versions'.",
    "APIError": "Google từ chối: chưa bật Google Sheets API, hoặc chưa chia sẻ Sheet cho client_email.",
    "ValueError": "private_key sai định dạng: giữ nguyên các ký tự \n trong chuỗi.",
}


def main() -> int:  # noqa: PLR0911 - mỗi lỗi thiết lập thoát sớm kèm một hướng dẫn riêng
    if not SECRETS.exists():
        print("Chưa có .streamlit/secrets.toml. Copy từ .streamlit/secrets.toml.example rồi điền.")
        return 1
    cfg = tomllib.loads(SECRETS.read_text(encoding="utf-8")).get("gsheets")
    if not cfg:
        print("secrets.toml chưa có mục [gsheets].")
        return 1
    missing = [k for k in REQUIRED if not cfg.get(k) or "<" in str(cfg[k])]
    if missing:
        print("Còn thiếu hoặc còn giá trị mẫu ở:", ", ".join(missing))
        return 1
    try:
        import gspread
    except ImportError:
        print("Chưa cài gspread. Chạy: pip install gspread")
        return 1
    info = {k: v for k, v in cfg.items() if k != "spreadsheet"}
    try:
        sheet = gspread.service_account_from_dict(info).open_by_url(cfg["spreadsheet"])
        ws = sheet.worksheet("versions")
        header, rows = ws.row_values(1), max(len(ws.col_values(1)) - 1, 0)
    except Exception as exc:  # không in thông báo gốc: có thể kèm chi tiết kết nối
        name = type(exc).__name__
        print(f"LỖI ({name}): {HINTS.get(name, 'xem lại các bước thiết lập.')}")
        return 1
    print(f"Kết nối OK. Tài khoản dịch vụ: {cfg['client_email']}")
    print(f"Tab 'versions': {rows} dòng dữ liệu.")
    if header[: len(HEADERS)] != HEADERS:
        print("Dòng tiêu đề CHƯA đúng. Cần đúng thứ tự A1:H1 =", " | ".join(HEADERS))
        return 1
    print("Dòng tiêu đề đúng.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
