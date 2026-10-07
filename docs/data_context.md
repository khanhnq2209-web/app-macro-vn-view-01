# Data context — `data/raw/` (2026-10-06)

Mục đích project: kho dữ liệu vĩ mô theo dõi yếu tố tác động **thị trường BĐS Việt Nam**. Dữ liệu dưới đây là raw nhập tay (Excel/CSV), chưa clean; không có cột nhạy cảm (toàn số liệu công khai). Kế hoạch bổ sung FRED + Yahoo Finance: xem `docs/spec.md`.

## Quy ước chung

- Nhiều file có **2 sheet cùng dữ liệu**: `Sheet1` dạng long (1 cột ngày + các cột chỉ tiêu) và 1 sheet wide gốc (dòng = chỉ tiêu, cột = ngày dạng chuỗi `dd-mm-yyyy` / `mm-yyyy` / `Qn-yyyy`). **Ưu tiên đọc `Sheet1`.**
- Header tiếng Việt có dấu, một số có khoảng trắng thừa đầu/cuối (vd `"Ngày "`) → strip khi đọc.
- Lãi suất ở đơn vị **%** (6.0 = 6%), trừ `09` và **`06`** (tỷ lệ thập phân, 0.045 = 4,5% — loader nhân 100).
- Ngày tháng/quý = ngày cuối kỳ (month-end / quarter-end).

## Danh mục file

| File | Sheet đọc | Grain | Khoảng thời gian | Cột / nội dung | Đơn vị, ghi chú |
|---|---|---|---|---|---|
| `01_deposit rate.xlsx` | `LS Lãi tiền gửi` (long, 147k dòng) | ngày quan sát × NH × kỳ hạn | 2016-01-03 → 2026-08-10 | `ngay_du_lieu, ma_ngan_hang, ten_ngan_hang, ma_ck, ky_han, lai_suat_pct` | `ky_han` ∈ {1,3,6,9,12,24}_thang; 20 NH; ngày quan sát không đều (chủ yếu CN/T2/T6) |
| `03_tctd.xlsx` | Sheet1 | 1 dòng = NH | — | `ma_ngan_hang, ten_ngan_hang, Big4, Big 10` | Dim NH; join với `01` qua `ma_ngan_hang`; Big4 = 4 NH; cờ `Big 10` chỉ có 6 NH được đánh dấu |
| `04_money supply.xlsx` | Sheet1 | quý → tháng | 2009-03 → 2026-05 | `Ngày, Cung tiền M2, Tăng trưởng Cung tiền M2 so với cuối năm, Tiền gửi TCKT, Tiền gửi dân cư` | Mức: tỷ VND `[suy luận]`; tăng trưởng: % YTD; giai đoạn đầu theo quý |
| `05_credit growth.xlsx` | Sheet1 | quý → tháng | 2009-03 → 2026-05 | `Tín dụng` + dư nợ theo ngành (Nông lâm thủy sản, Công nghiệp, **Xây dựng**, Thương mại, Vận tải viễn thông, Khác) + `Tăng trưởng ...` (% YTD) | Không có ngành BĐS riêng |
| `06_LS sbv.xlsx` | Sheet1 | ngày làm việc | 2016-01-04 → 2026-08-03 | OMO: KL phát hành / đáo hạn / lưu hành tín phiếu & reverse repo, bơm hút ròng · LS tái chiết khấu, tái cấp vốn · LS BQ liên NH (ON, 1W, 2W, 1M, 3M, 6M, 9M) + doanh số tương ứng | **LS lưu dạng thập phân** (0.045) — đã xác minh 2026-10-06; KL/doanh số: tỷ VND `[suy luận]` |
| `07_CPI.xlsx` | Sheet1 | tháng | 2002-01 → 2026-07 | `Date, Chỉ tiêu (mm-yyyy), CPI`, 11 nhóm hàng (có **Nhà ở và vật liệu xây dựng**), `Lạm phát cơ bản` | **% so tháng trước (MoM)** — đã xác minh khớp 100% bảng dulieukinhte #318; nhãn "Điểm" ở sheet wide là sai. YoY = tích 12 tháng MoM |
| `09_dự trữ bắt buộc.xlsx` | Sheet1 | sự kiện (ngày hiệu lực) × nhóm TCTD | 2009-03 → 2018-06 | `Hiệu lực từ, Văn bản, Nhóm tổ chức tín dụng`, tỷ lệ DTBB VND/ngoại tệ theo kỳ hạn | **Tỷ lệ thập phân** (0.03 = 3%); ngày `dd/mm/yyyy`; nhóm TCTD là chuỗi dài, tên nhóm đổi qua các văn bản |
| `10_Trần lãi suất huy động.xlsx` | Sheet1 | sự kiện (12 quyết định) | 2014-03 → 2024-11 | `Quyết định, Ngày ký, Ngày hiệu lực, QĐ bị thay thế`, trần KKH&<1T, 1–<6T (TCTD thường), 1–<6T (QTDND/TCVM), ≥6T | Số dạng chuỗi **dấu phẩy thập phân** (`"5,5"`); cột ≥6T = chuỗi "TCTD tự ấn định"; ngày `dd/mm/yyyy` |
| `11_GDP.xlsx` | Sheet1 | quý | Q1-2010 → Q2-2026 | `Ngày, Chỉ tiêu (Qn-yyyy)`, GDP giá so sánh + khu vực (NLTS, CN&XD, CN, **Xây dựng**, Dịch vụ, Thuế) | tỷ VND; nghi có rebase/đứt gãy 2026 → kiểm YoY |
| `GDP - Copy.xlsx` | — | — | — | **Trùng `11_GDP.xlsx`** | Bỏ qua |
| `GDP-hien-hanh.xlsx`, `GDP-So-Sanh.xlsx` | sheet wide duy nhất | quý (cột `Qn-yyyy`) | Q1-2010 → ~2026 | 27 ngành chi tiết, có **Hoạt động kinh doanh bất động sản**, Xây dựng, Tài chính NH | tỷ VND; giá hiện hành / giá so sánh |
| `12_Dau tu cong.xlsx` | Sheet1 | tháng | 2010-01 → 2026-06 | `Tổng, Trung ương, Địa phương`; sheet wide thêm theo Bộ (có Bộ Xây dựng) và theo tỉnh (HCM, HN, …) | **Tỷ đồng, số từng tháng (không lũy kế)** — đã xác minh với dulieukinhte #317; nhãn "Triệu USD" ở tên sheet là sai. T9 và T10/2025 trùng giá trị (86.622) → nghi lỗi nguồn |
| `13_Loi-suat-TPCP.xlsx` | sheet wide duy nhất | ngày | 2013-03-19 → 2026-08-12 | Lợi suất thứ cấp 3M–20Y; LS trúng thầu sơ cấp 3Y/5Y/10Y/15Y/30Y | %; dòng tiêu đề nhóm xen giữa các dòng số |
| `18_XNK.xlsx` | Sheet1 | tháng | 2009-01 → 2026-07 | Nhập/Xuất khẩu: Tổng, khu vực trong nước, khu vực FDI | triệu USD |
| `19_Ty-gia-trung tam USDVND.xlsx` | Sheet1 (chỉ `Trung tâm`) / wide (thêm trần, sàn, mua, bán) | ngày | 2009-01-03 → 2026-08-10 | Tỷ giá trung tâm SBV | VND/USD |
| `20_Ty gia VCB.xlsx` | Sheet1 (long, 82k dòng) | ngày × ngoại tệ | 2015-01-01 → 2026-08-06 | `ngay, ma_ngoai_te, ten_ngoai_te, mua_tien_mat, mua_chuyen_khoan, ban` | 20 ngoại tệ (USD, EUR, JPY, CNY, KRW, SGD, THB, …); VND/đơn vị ngoại tệ |
| `Von-FDI-dang-ky-cap-moi.xlsx` | sheet wide duy nhất | tháng (cột `mm-yyyy`, **không liên tục**) | 2019-06 → 2026-07 | Tổng vốn đăng ký cấp mới + theo địa phương + theo quốc gia | triệu USD; **không có theo ngành**; **lũy kế từ đầu năm (YTD)** — đã xác minh với dulieukinhte #405; tháng thiếu → không suy ra số từng tháng được |
| `21_lai_suat_fed_effr.csv` | — | ngày làm việc | 2015-01-02 → 2026-07-29 | `ngay_hieu_luc, lai_suat_effr_pct, target_rate_from_pct, target_rate_to_pct, percentile_{1,25,75,99}_pct, doanh_so_ty_usd, intraday_thap/cao_pct, do_lech_chuan_pct, da_dieu_chinh` | % ; ngày ISO |
| `Lai-suat-Fed.json` | key `series` (7 series, 20.656 kỳ ngày) | ngày | 1970 → nay | Target trần/sàn, EFFR H.15, EFFR, SOFR, OBFR, IORB | %; **dùng JSON thay cho `Lai-suat-Fed.xlsx`** — bản xlsx bị cắt ở 2014-11 do giới hạn 16.384 cột Excel |
| `23_ yeild curve US.xlsx` | sheet wide duy nhất (14k cột) | ngày | 1970 → 2026-08-07 | UST 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y; spread 10Y−2Y, 10Y−3M | % |
| `24_Chi-so-USD-DXY.xlsx` | Sheet1 | ngày (có cả cuối tuần, NaN) | 2017-12-01 → 2026-08-09 | `Chỉ số USD (DXY)`; sheet wide từ 2015 thêm Fed target trên + UST 10Y | điểm |
| `25_TQ Lai-suat-dieu-hanh.xlsx` | Sheet1 | sự kiện (ngày thay đổi) | 1996-05 → 2026-07 | LPR 1Y/5Y, MLF 1Y, SLF ON/7D/1M, LS dự trữ vượt mức, tái chiết khấu, RRR TCTD lớn / vừa-nhỏ | %; thưa (chỉ dòng khi có thay đổi) → ffill |
| `26_TQ Ty-gia-nhan-dan-te.xlsx` | Sheet1 | tháng | 1999-12 → 2026-07 | `USD/CNY cuối kỳ, USD/CNY bình quân kỳ, SDR/CNY cuối kỳ` | CNY/USD |
| `28.1_Muc-tieu-Chinh-phu.xlsx` | Sheet1 | năm (ngày 31/12) | 2011 → 2026 | Cặp `<chỉ tiêu> - Mục tiêu` / `- Thực hiện`: tăng trưởng GDP, CPI BQ, GDP/người, năng suất LĐ, thất nghiệp đô thị, bội chi NSNN, … | %, đơn vị theo chỉ tiêu; năm hiện hành chỉ có mục tiêu |

## Liên quan trực tiếp BĐS (đã có)

GDP ngành **Kinh doanh BĐS** và **Xây dựng** (quý) · tín dụng ngành **Xây dựng** · CPI nhóm **Nhà ở & VLXD** · đầu tư công (Bộ Xây dựng, theo tỉnh) · FDI theo địa phương. **Chưa có:** giá/nguồn cung/giao dịch BĐS, tín dụng BĐS riêng, FDI vào BĐS.

## Nguồn gốc file (đã xác minh 2026-10-06)

- `01_deposit rate` ← **Simplize** (đã có giấy phép; app cập nhật bằng API, đến 06/10/2026) (API `api2.simplize.vn/api/historical/interest-rate/{TICKER}`; VCB khớp 8.020/8.020 dòng).
- Các file Excel còn lại (sheet "Chỉ tiêu" + cột ngày, `Lai-suat-Fed.json`) ← nút "Xuất dữ liệu" của **dulieukinhte.com** (khớp từng ô: USDVND, DXY, LPR TQ, CNY, FDI, CPI MoM).

## Vấn đề dữ liệu đã biết

- **Tín dụng (`05`)**: T2 và T3/2026 lặp y hệt (3,18%); chuỗi dư nợ lệch với cột % (năm 2025: 20,49% tính từ dư nợ so với 19,07% ghi trong file, VBMA 19,1%). App tính tín dụng so cùng kỳ từ cột %. Năm 2018 cột % lệch VBMA khoảng 3 điểm % (VBMA ghi 2017 = 18,2%, file ghi 14,97%).
- **Đầu tư công (`12`)**: T9 và T10/2025 lặp y hệt (86.622). App gắn cờ "lặp số kỳ trước".
- **FDI**: file là vốn đăng ký **cấp mới**; heatmap VBMA là tổng vốn đăng ký (gồm điều chỉnh, góp vốn), không so trực tiếp được. T3/2026 tăng 6,7 tỷ USD trong một tháng, chưa kiểm nguồn.

- **`07_CPI.xlsx` sai MoM T12/2022 (4,55) và T1/2023 (3,37)**, giống số so cùng kỳ nhập nhầm cột (cả CPI chung và nhóm nhà ở). YoY tự tính lệch tới 7,9 điểm % suốt 2023. App dùng CPI so cùng kỳ công bố của VBMA (2017→nay), chỉ tự tính cho tháng VBMA không có. Cần sửa ở nguồn rồi xuất lại.

- **`GDP-So-Sanh.xlsx` / `11_GDP.xlsx` có 2 điểm gãy năm gốc: Q1/2021 (706 → 1.195 nghìn tỷ) và Q1/2026** → YoY tự tính qua điểm gãy sai (Q1/2021 = +69%). App dùng **tăng trưởng GDP công bố từ VBMA** (`vbma.gdp_yoy`) làm chỉ số đại diện; chuỗi tự tính giữ để đối chiếu, gắn cờ.
- **GDP (`11`, GDP-*) đã bị nguồn sửa lùi**: GDP giá so sánh trên dulieukinhte khác toàn bộ trước 2026; giá hiện hành khác trước 2020. File local là vintage cũ → khi refresh phải kéo lại toàn bộ lịch sử, không nối thêm.
- CPI dạng chỉ số trên nguồn (dulieukinhte #272) đổi gốc giữa 10/2025 và 11/2025 → chỉ dùng MoM để tính YoY.
- `21`/`23`/`24`/`Lai-suat-Fed.*` sẽ được thay bằng FRED/Yahoo (crawler), giữ để đối chiếu.

## Lỗi dữ liệu phát hiện 06/10/2026 (dulieukinhte, chưa sửa ở nguồn)

| Chuỗi | Hiện tượng | Ảnh hưởng |
|---|---|---|
| `vn.m2_ytd` | 9/2025 là 11,53% rồi 10/2025 tụt về 4,54% (lũy kế từ đầu năm không thể giảm như vậy); từ đó M2 so cùng kỳ chỉ còn 5–9% | `credit_minus_m2` sai từ 10/2025; đã bỏ khỏi scorecard. Cần kiểm lại file xuất |
| `vn.credit_ytd` | 3/2026 = 2/2026 = 3,18% (lặp số) | `credit_yoy` tháng 3/2026 có thể sai |
