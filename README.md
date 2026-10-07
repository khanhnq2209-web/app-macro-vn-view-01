# App theo dõi vĩ mô — yếu tố tác động thị trường BĐS Việt Nam

App Streamlit cho team quản trị rủi ro: theo dõi chỉ số vĩ mô quốc tế + Việt Nam, trạng thái theo ngưỡng (xanh/vàng/đỏ), tác động tới BĐS (nhà ở / KCN), FedWatch. Spec và quyết định: [docs/spec.md](docs/spec.md). Schema dữ liệu raw: [docs/data_context.md](docs/data_context.md).

## 1. Chạy

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt -e .   # -e . để mọi trang import được macro_app
copy .env.example .env        # điền FRED_API_KEY, ADMIN_PASSWORD; APP_MODE=admin khi chạy local

$env:PYTHONPATH = "src"
.venv\Scripts\python -m macro_app.cli refresh   # tải FRED, Yahoo, FedWatch, Simplize, VBMA rồi build
.venv\Scripts\python -m macro_app.cli build     # chỉ tính lại từ raw + cache (không gọi mạng)
.venv\Scripts\streamlit run app.py
```

| Lệnh | Việc |
|---|---|
| `cli refresh --sources fred,yahoo` | Tải lại một số nguồn (fred, yahoo, fedwatch, simplize, vbma, lme) rồi build |
| `cli merge-inbox` | Gộp file Excel trong `data/inbox/` vào `data/raw/` rồi build |
| `pytest` | Test (không gọi mạng). `pytest -m live` gọi mạng thật |
| `python scripts/screenshots.py --port 8501 --password ...` | Chụp toàn bộ trang vào `docs/screenshots/` |

Luồng dữ liệu: `data/raw/` (Excel VN) + `data/cache/*.xlsx` (FRED, Yahoo, VBMA, FedWatch — mỗi chỉ số 1 sheet, sheet `_meta` ghi thời điểm tải) → **build** → `data/app/` (app đọc) + `data/public/` (file công khai: `series/<mã>.csv`, `latest.csv`, `dictionary.csv`, `status_history.csv` — không chứa số Yahoo).

## 2. Chế độ truy cập

- **Công khai (mặc định)**: chỉ xem, không có đăng nhập, ẩn số vendor (Yahoo, LME). Bản deploy để trống `APP_MODE`. Mọi thao tác ghi làm ở máy local rồi commit (D1).
- **Quản trị (chạy local)**: đặt `APP_MODE=admin` + `ADMIN_PASSWORD` trong `.env` hoặc `.streamlit/secrets.toml` (mẫu: `secrets.toml.example`). Sidebar → "Đăng nhập quản trị" (tên + mật khẩu). Mở khóa: sửa ngưỡng, nút **Refresh dữ liệu**, gộp inbox, lưu view dùng chung, số FedWatch của CME.
- **Chế độ trình bày**: toggle ở sidebar (hoặc thêm `?present=1` vào URL) — ẩn khung Streamlit, chữ to, 6 card/hàng; chụp ở 1920×1080 cho slide. Nút "Thoát chế độ trình bày" ở cuối trang.

## 3. Thêm chỉ số

1. Nếu là series quốc tế mới: thêm mã vào `config/sources.yaml` (mục `fred:` hoặc `yahoo:`), chạy `cli refresh --sources fred`.
2. Thêm 1 mục vào `config/catalog.yaml`: `code, name, group (A1…E1), unit, frequency, source, recipe, change_unit, direction, segment` (+ `target`, `flags`, `representative` nếu cần). Recipe có sẵn: `raw`, `extend`, `yoy`, `mom_to_yoy`, `mom_to_avg_ytd`, `ytd_change_pct`, `ytd_sum_yoy`, `quarter_last`, `deposit_avg`, `diff`, `manual`.
3. Đưa mã vào `config/views.yaml` (card Tổng quan / chart) hoặc thêm qua trang **Tùy chỉnh hiển thị**.
4. `cli build`. Không cần sửa code giao diện.

## 4. Điền ngưỡng

- Mặc định mọi chỉ số dùng **ngưỡng thống kê** (`config/thresholds.default.yaml`: z-score vàng > 1, đỏ > 2, cửa sổ 5 năm). App ghi rõ "ngưỡng thống kê mặc định" cho chỉ số chưa có ngưỡng nghiệp vụ.
- Ghi đè: trang **Ngưỡng** (quản trị) → sửa bảng → **Lưu** (ghi `config/thresholds.d/90_ui.yaml` + lịch sử `config/thresholds_history.csv`), hoặc tạo file `config/thresholds.d/<tên>.yaml` (xem `10_example.yaml.example`). Ba kiểu: `zscore`, `target_band` (lệch mục tiêu Chính phủ, điểm %), `absolute` (khoảng giá trị).
- Quy tắc tác động BĐS: `config/impact_rules.yaml` (lấy nguyên từ báo cáo).

### Scorecard theo phân khúc

- Trang **Scorecard**: chọn bộ cấu hình → phân khúc → xem điểm, từng chỉ số, lịch sử.
- Trang **Cấu hình scorecard** (chỉ khi chạy local `APP_MODE=admin`):
  - Bảng chỉ số bên trái, bấm một dòng để sửa ở bên phải. Thứ tự sửa: đo gì → kiểu ngưỡng → chiều → số mức và mốc; mốc nhập kiểu `4,75; 5,5; 6,25; 7`, có nút **Gợi ý mốc**.
  - Mọi thay đổi vào **bản nháp**, điểm nháp tính lại ngay. Bấm **Lưu** mới ghi file; **Bỏ thay đổi** để quay lại.
  - Nút **Phân khúc**: thêm (trống hoặc sao chép), đổi tên, xóa. Nút **Quản lý bộ**: đổi tên, đặt mặc định, lưu thành bộ mới, tạo bộ trống, xóa bộ.
- File: `config/profiles/<bộ>/profile.yaml` + `segments/*.yaml`; bộ mặc định ở `config/profiles/_default.yaml`; thang điểm và dải xếp hạng ở `config/scorecard.yaml`.
- Phương pháp và căn cứ từng mốc: `docs/spec.md` mục Scorecard, `docs/plan_scorecard_v2.md`.
- Dự báo ghép vào scorecard: dòng có dự báo (lãi Fed theo FedWatch) hoặc mục tiêu Chính phủ (GDP, tín dụng) ghi thêm "Kỳ vọng" / "Mục tiêu" và mức tương ứng; đầu trang có điểm "nếu theo dự báo". Chỉ để suy luận thô, không vào điểm chính.
- Trang **Kế hoạch & dự báo**: xem và sửa bản đồ chỉ số thực tế → kế hoạch / dự báo (mục tiêu CP, FedWatch, chỉ số khác, hoặc nhập tay số mục tiêu). File: `config/forecast_map.yaml`.
- Đề xuất nâng cấp: `docs/roadmap.md`.

## 5. Cập nhật dữ liệu Việt Nam

| Nguồn | Cách cập nhật |
|---|---|
| LS huy động (Simplize, đã có giấy phép) | Tự động: Refresh → "Lãi suất huy động" (nối thêm vào `01_deposit rate.xlsx`, sao lưu trước khi ghi) |
| dulieukinhte.com (CPI, tỷ giá, TPCP, GDP, FDI, đầu tư công…) | Xuất Excel từ site → bỏ vào `data/inbox/` → `cli merge-inbox` (hoặc nút "Gộp file trong data/inbox"). Kỳ trùng: bản mới thắng (nguồn có sửa số cũ); log ô bị đổi ở `data/raw/_merge_log.csv`. File 04, 05, 06, 11 chỉ có sheet dạng dọc → export phải cùng bộ cột mới khớp |
| VBMA (PMI, GDP công bố, thu tiền sử dụng đất) | Tự động: Refresh → VBMA |
| Đồng LME (giá chính thức cash, 3 tháng, tồn kho — qua Westmetall) | Tự động: Refresh → Đồng LME |
| Số nhập tay (nếu cần) | App không có form: điền thẳng `data/raw/manual/manual_inputs.csv` + thêm chỉ số `recipe: {op: manual}` vào catalog |

GitHub Actions (`.github/workflows/daily-refresh.yml`) chạy FRED + Simplize + LME 08:00 thứ 2–6 (build lỗi → không commit), commit nếu có thay đổi (cần secret `FRED_API_KEY`).

## 6. Lưu ý dữ liệu

- `GDP-So-Sanh.xlsx` có điểm gãy năm gốc (Q1/2021, Q1/2026) → GDP tự tính từ mức bị gắn cờ; chỉ số đại diện dùng **tăng trưởng GDP công bố (VBMA)**. Cần xuất lại chuỗi GDP mới từ dulieukinhte để sửa tận gốc.
- FedWatch: bản công khai hiện số **tự tính** từ giá ZQ (Yahoo) theo phương pháp CME; quản trị xem thêm số CME QuikStrike để đối chiếu (lệch ≤ ~2 điểm %).
- Guard: `pre-commit install` — chặn commit `.env`, file trong `data/inbox/`, `data/raw/_backup/`, file > 20 MB, secret.

Code/dữ liệu của project dự báo LS huy động cũ: git history + quarantine `C:\tmp\interest-rate-forecast-quarantine-20260922-172624`.
