# Spec: App theo dõi vĩ mô — yếu tố tác động thị trường BĐS VN

Ngày: 2026-10-06 | Chế độ: FAST | Trạng thái: **đã build đợt 1a, 1b, 2 — chờ UAT** | Yêu cầu gốc: prompt "App theo dõi vĩ mô (Streamlit)" (người dùng dán trong hội thoại 2026-10-06)

## Mục tiêu + Audience

App Streamlit cho team quản trị rủi ro theo dõi yếu tố vĩ mô (VN + quốc tế) tác động thị trường BĐS VN. Người dùng không chuyên kỹ thuật; màn hình Tổng quan được chụp vào slide; deploy công khai chỉ đọc.

## Quyết định đã chốt (2026-10-06)

| # | Quyết định |
|---|---|
| D1 | Bản deploy công khai **chỉ đọc** `data/public/` đã commit. Mọi thao tác ghi (ngưỡng, nhập tay, refresh) chạy **local** (`APP_MODE=admin`) hoặc GitHub Actions rồi commit. |
| D2 | Dữ liệu (raw + public + cache) **commit vào repo**. |
| D3 | Ngưỡng = **config**: file mặc định `config/thresholds.default.yaml` (zscore vàng >1, đỏ >2, có `min_points`); người dùng ghi đè hoặc thêm file/bảng config riêng (`config/thresholds.d/*.yaml`, nạp sau đè trước). UI ghi rõ "ngưỡng thống kê mặc định" khi chưa ghi đè. |
| D4 | LS huy động: ffill từng NH × kỳ hạn lên lịch ngày rồi mới bình quân; hiển thị cả **Big4** và **20 NH**. `[giả định: Big4 12T là chỉ số đại diện nhóm B3]` |
| D5 | Đơn vị đã xác minh (xem `docs/data_context.md`): CPI = MoM %; đầu tư công = tỷ đồng/tháng; FDI = lũy kế YTD. Bỏ cờ "đơn vị chưa xác minh" cho 3 chỉ số này; FDI giữ cờ "lũy kế". |
| D6 | **Simplize: đã có giấy phép dữ liệu.** Crawler gọi API, **append/upsert vào `01_deposit rate.xlsx`** theo khóa `(ngay_du_lieu, ma_ngan_hang, ky_han)`; được hiển thị cả số từng NH. |
| D7 | **dulieukinhte: người dùng tự xuất Excel** từ site rồi bỏ vào thư mục nhập (`data/inbox/`); tool **gộp vào file raw đang có** cùng chỉ tiêu: kỳ trùng → bản mới thắng (nguồn có sửa lùi), ghi log ô bị đổi giá trị. Không gọi API nội bộ của site. |
| D8 | **FRED + Yahoo: chọn nguồn theo từng chỉ số**, lấy dư thêm series dự phòng; lưu **Excel** `data/cache/{fred,yahoo}.xlsx` (sheet/series + sheet `_meta`); app có **nút "Cập nhật dữ liệu"** (chạy local). |
| D10 | **Đồng = giá LME** (official cash, Westmetall, ngày, 2010→); COMEX (Yahoo) giữ để đối chiếu. Yahoo không có LME. |
| D11 | **Đơn giản hóa: trọng tâm dashboard + ngưỡng, không có form nhập.** Bỏ trang Nhập tay + gợi ý AI; bỏ 3 chỉ số nhập tay (thuế quan Mỹ, IMF, lãi vay mua nhà) → nhóm A4 và A5 (tăng trưởng toàn cầu) chưa có chỉ số đại diện trong ma trận tác động. |
| D9 | Thêm bảng **FedWatch** vào trang Quốc tế: ma trận xác suất khoảng lãi suất × 10 kỳ họp FOMC tới + chart lịch sử xác suất. Nguồn chính: CSV từ iframe QuikStrike của CME; dự phòng: tự tính từ giá ZQ (Yahoo) — xem bảng Nguồn. |
| D12 | **Bộ cấu hình scorecard** có tên, chứa nhiều phân khúc (ngưỡng màn Tổng quan giữ riêng ở bộ ngưỡng). Sửa ở trang riêng **Cấu hình scorecard** (chỉ khi quản trị) trên **bản nháp + nút Lưu**; có Lưu thành bộ mới / Tạo bộ trống / Đặt mặc định / Xóa bộ. Bộ hiện có: **Theo dõi BĐS - 01** (toàn ngưỡng cứng, trụ cột chia đều). |
| D13 | **Dự báo ghép vào scorecard (thô, không vào điểm chính):** lãi Fed ↔ FedWatch (CME, dự phòng tự tính ZQ); CPI/GDP/tín dụng ↔ mục tiêu Chính phủ năm nay. Mỗi dòng ghi mức của dự báo theo ngưỡng của dòng; đầu trang có điểm "nếu theo dự báo/mục tiêu". Danh sách nâng cấp tiếp: `docs/roadmap.md`. |
| D14 | **Bản đồ kế hoạch / dự báo** `config/forecast_map.yaml`, sửa ở trang **Kế hoạch & dự báo** (quản trị, bấm Lưu). Mỗi dòng: chỉ số thực tế ← nguồn: `target` (mục tiêu CP năm nay), `fedwatch` (upper/lower/effective, kỳ họp cuối năm), `indicator` (chỉ số khác, kỳ mới nhất), `manual` (nhập tay giá trị + kỳ). Chỉ tiêu tín dụng gắn với tín dụng **so với đầu năm**. Hiện ở cột Kế hoạch / Dự báo của scorecard, không vào điểm. Font: toàn app dùng Source Sans (bỏ font có chân cho số). |

## Nguồn dữ liệu

| Nguồn | Dữ liệu | Truy cập | Điều khoản | Dùng cho |
|---|---|---|---|---|
| `data/raw/` (27 file) | VN + quốc tế, vintage nhập tay | file | — | nền lịch sử |
| **Simplize** | LS huy động 20 NH, kỳ hạn 1–24T, ngày, 2016 → hôm nay. **Là nguồn gốc của `01`** | API JSON công khai `api2.simplize.vn/api/historical/interest-rate/{TICKER}` + `/api/company/interest-rate/list` | **Đã có giấy phép** (D6) | refresh `01` hằng ngày |
| **dulieukinhte.com** | 119 bộ VN: CPI (chỉ số/MoM/YoY), tín dụng YTD theo ngành, LS cho vay BQ (từ 03/2024), đầu tư công, vốn ĐT toàn xã hội, GDP ngành (KD BĐS, Xây dựng), thép, BĐS Bộ XD (từ Q4/2025). **Là nguồn gốc các file Excel còn lại** | API chính thức `api.dulieukinhte.com/v1` (Bearer key; Free 100 req/tháng + 5 năm lịch sử; **Pro 299.000đ/tháng**). API nội bộ `/api/internal/...` bị **robots.txt cấm** | yêu cầu dẫn nguồn khi công bố lại | xuất Excel tay → gộp (D7) |
| **VBMA** | File CSV tĩnh: heatmap vĩ mô T1/2017→T8/2026 (CPI Nhà ở & VLXD YoY, PMI, tín dụng ngành YTD, ngân sách); GDP ngành KD BĐS theo quý từ 2015; **thu tiền sử dụng đất** theo năm; TPCP thứ cấp/đấu thầu/lịch đáo hạn | `vbma.org.vn/csv/markets/{charts,tables}/vi/<file>.csv` (UTF-16 + tab, không cần đăng nhập). TPDN BĐS **cần tài khoản hội viên** | robots cho phép; không có ToS; quyền phân phối lại chưa rõ | PMI, thu tiền SDĐ (nhóm C1), đối chiếu |
| FRED | Fed, UST, USD broad, Brent, HY spread, breakeven, nhà ở Mỹ | API + `FRED_API_KEY` | public domain phần lớn | nhóm A |
| Yahoo Finance | DXY, đồng COMEX, Brent mới nhất, giá ZQ từng tháng (`ZQV26.CBT`…) | `yfinance` 1.2.0 (đã cài; gọi chart API thô bị 429) | cấm phân phối lại | nhóm A (D8) |
| **CME FedWatch (QuikStrike)** | Xác suất FedWatch y hệt site CME, 10 kỳ họp, lịch sử ~250 phiên theo ngày | `cmegroup-tools.quikstrike.net/User/QuikStrikeView.aspx?viewitemid=IntegratedFedWatchTool` → POST tab Downloads → CSV `Export/FedWatch/AllMeetings.aspx`; không cần đăng nhập, 3 request. Dữ liệu cuối ngày | dữ liệu CME, nhiều khả năng cấm cào/phân phối lại `[chưa kiểm ToS]` | D9 nguồn chính |
| FedWatch tự tính | Xác suất theo phương pháp FedWatch từ giá ZQ (Yahoo) + lịch FOMC (federalreserve.gov) + DFEDTARU/L, EFFR (FRED) | code | dữ liệu đầu vào công khai | D9 dự phòng, đối chiếu QuikStrike lệch ≤ 2 điểm % |
| Đối chiếu khác | Atlanta Fed Market Probability Tracker (`mpt_histdata.xlsx`, SOFR options, theo **quý**, 2023→); Kalshi API (`KXFEDDECISION-*`, thị trường dự đoán); CME FedWatch EOD API trả phí (~25 USD/tháng, lịch sử từ 2015) | — | — | tùy chọn |

Lưu ý mạng: từ máy hiện tại **không vào được cmegroup.com, investing.com, polymarket** (bị reset ở tầng mạng); QuikStrike, Yahoo, FRED, federalreserve.gov, Kalshi vào được.

Lưu ý chung: dulieukinhte sửa lùi số (GDP) và đổi gốc (CPI chỉ số) → mỗi lần refresh **kéo lại toàn bộ lịch sử**, lưu vintage, so chênh lệch với lần trước.

## Giả định đã áp dụng khi build (người dùng vắng, "làm all") — kiểm khi UAT

- [giả định] FedWatch bản công khai = số **tự tính** từ giá ZQ (Yahoo); số CME QuikStrike chỉ hiện ở chế độ quản trị.
- [giả định] Yahoo vẫn hiển thị trong app (D8), nhưng **không** ghi ra `data/public/` (latest.csv để trống giá trị, cờ `yahoo_hidden`).
- [giả định] Chỉ số đại diện B1 = **tăng trưởng GDP công bố (VBMA)**, vì `GDP-So-Sanh.xlsx` có điểm gãy năm gốc Q1/2021 và Q1/2026 (YoY tự tính = +69% Q1/2021). Chuỗi tự tính giữ để đối chiếu + cờ "nghi đổi năm gốc".
- [giả định] Chỉ số đại diện từng nhóm: A1 Fed biên trên · A2 Brent · A3 đồng COMEX · A4 thuế quan · A5 tăng trưởng IMF · B1 GDP công bố · B2 CPI YoY · B3 LS huy động 12T Big4 · B4 tín dụng YTD · C1 thu tiền SDĐ · D2 đầu tư công · E1 FDI.
- [giả định] Card chuỗi ngày ghi thay đổi **so 30 ngày trước** (so ngày liền trước quá nhiễu); tháng/quý ghi so kỳ trước.
- [giả định] Nhóm đi ngang → mọi ô tác động "●". D2, E1 chưa có quy tắc trong báo cáo → "Chưa có quy tắc", không tự suy.
- [giả định] App không tự gọi API khi mở; chỉ gọi khi bấm Refresh / CLI / Actions. Cache cũ hơn 24h → banner "Dữ liệu từ cache ngày …".
- [giả định] Trục phụ chỉ cho phép trong view tùy chỉnh (prompt yêu cầu); view mặc định không dùng.
- Không làm: lưu view trong localStorage trình duyệt (bản công khai: view theo phiên + xuất/nhập YAML).

## Scorecard theo phân khúc (quyết định 06/10/2026, ĐỀ XUẤT, chờ duyệt)

Phương pháp: tham chiếu OECD/JRC *Handbook on Constructing Composite Indicators* (quy chuẩn, trọng số đều, cộng tuyến tính) và ECB/ESRB *RRE heatmap* (chấm mức rồi tổng hợp).

**Bộ cấu hình** (D12, 06/10/2026): mỗi bộ có tên, gồm nhiều phân khúc; mỗi phân khúc có chỉ số, trụ cột, trọng số, ngưỡng từng dòng. Lưu ở `config/profiles/<bộ>/` (`profile.yaml` + `segments/*.yaml`), bộ mặc định ở `config/profiles/_default.yaml` (hiện ở Tổng quan). Trang **Cấu hình scorecard** sửa trên bản nháp trong phiên, điểm nháp tính lại ngay; bấm **Lưu** mới ghi file, **Lưu thành bộ mới** để tách phiên bản. Trang Scorecard chỉ xem bản đã lưu. Build chấm mọi bộ, mọi phân khúc.

| Thành phần | Quy tắc | Nguồn cấu hình | Người xác nhận |
|---|---|---|---|
| Mức → điểm | 5 mức +2 · +1 · 0 · −1 · −2 (4 mức +1 · 0 · −1 · −2; 3 mức +1 · 0 · −1), sửa được từng dòng | `config/scorecard.yaml` | |
| Trọng số | Chia đều theo trụ cột, rồi chia đều trong trụ cột. Ghi `weight` thì dùng, dòng để trống nhận trung bình các `weight` đã ghi; chuẩn hóa về 1 | `config/profiles/*/segments/*.yaml` | |
| Điểm tổng | Σ điểm × trọng số / Σ trọng số của dòng có số; độ phủ < 60% → không chấm, đầu trang hiện điểm tháng gần nhất đủ dữ liệu | `config/scorecard.yaml` | |
| Số cũ | Kỳ mới nhất cũ hơn D/W 1, M 3, Q 4, A 13 tháng so với tháng chấm → không tính (áp như nhau cho hiện tại và lịch sử) | `config/scorecard.yaml` | |
| Xếp hạng | ≥ 0,8 Rất thuận lợi · ≥ 0,45 Thuận lợi · ≥ 0,05 Trung tính · ≥ −0,2 Bất lợi · còn lại Rất bất lợi. Hiệu chỉnh theo P90/P70/P30/P10 điểm tháng 10 năm của bộ Theo dõi BĐS - 01 (trung bình +0,3). Dùng chung mọi bộ | `config/scorecard.yaml` | |
| Lịch sử | Lưới cuối tháng, 10 năm, tới tháng chấm; mỗi tháng chỉ dùng dữ liệu tới tháng đó | `config/scorecard.yaml` | |

Bộ **Theo dõi BĐS - 01** (mặc định): toàn ngưỡng cứng 5 mức, trụ cột chia đều. Chi tiết từng dòng (cách đo, mốc, căn cứ, nguồn) ở `docs/plan_scorecard_v2.md` mục A và trong mô tả từng dòng của `config/profiles/theo_doi_bds_01/`.

| Phân khúc | Trụ cột → chỉ số | Người xác nhận |
|---|---|---|
| Nhà ở (9) | Chi phí vốn: LS huy động 12T Big4, TPCP 10 năm (thay đổi 12 tháng) · Tín dụng và thanh khoản: tín dụng so cùng kỳ (**hai phía**, 11–15% tốt nhất), liên NH qua đêm (TB 20 phiên) · Cầu và thu nhập: GDP · Ổn định vĩ mô: CPI, CPI nhà ở & VLXD, tỷ giá % so cùng kỳ · Hạ tầng: đầu tư công (tổng 12 tháng, % so cùng kỳ) | |
| KCN (10) | FDI và cầu thuê: FDI đăng ký (tổng 12 tháng, % so cùng kỳ) · Sản xuất và thương mại: PMI, xuất khẩu (TB 3 tháng), GDP · Chi phí vốn và rủi ro: LS huy động 12T, TPCP 10 năm (thay đổi 12 tháng), DXY % so cùng kỳ, VIX (TB 21 phiên) · Chi phí đầu vào: đồng LME, Brent (% so cùng kỳ) | |

Kiểm chứng (backtest 10 năm): Nhà ở Rất bất lợi 12/2022–4/2023; KCN Rất bất lợi 5/2020, 6–12/2021, 11/2022–3/2023. Mốc [NĐ] đã đối chiếu phân vị 10 năm; 4 mốc chỉnh theo dữ liệu (LS huy động, liên NH, FDI, đồng/Brent).

Giới hạn:
- Chưa có dữ liệu trái phiếu doanh nghiệp BĐS, LS cho vay thả nổi, tín dụng BĐS, hấp thụ/lấp đầy (mục E của kế hoạch).
- Tín dụng − M2 bỏ khỏi scorecard vì `vn.m2_ytd` lỗi từ 10/2025 (`docs/data_context.md`).
- FDI 12 tháng trượt chỉ có từ 12/2023.
- Chưa trừ độ trễ công bố.
- Trụ cột chia đều nên GDP và đầu tư công mỗi chỉ số chiếm 20% điểm Nhà ở.

## Đợt

| # | Đợt | DoD | Trạng thái | Ngày | Ghi chú |
|---|---|---|---|---|---|
| 1a | Guard + catalog + config + lớp dữ liệu (raw, Simplize, FRED, Yahoo, VBMA, FedWatch) → `data/public/` | pytest 101 pass; FRED khớp raw cũ (DFF vs `21`, DGS10 vs `23`: lệch 0,0000); FedWatch tự tính vs CME ≤ 0,022; pre-commit chặn `.env`/inbox | done — chờ UAT | 2026-10-06 | Simplize +6.210 dòng đến 06/10/2026 |
| 1b | 8 trang + chế độ trình bày + công khai/quản trị + Refresh + screenshot | AppTest 11 pass; nghiệm thu #6 (sửa ngưỡng → đỏ + history) và #9 (offline giữ cache + báo lỗi) đạt; ảnh `docs/screenshots/` | done — chờ UAT | 2026-10-06 | |
| 2 | Tùy chỉnh view (YAML), GitHub Actions, Thay đổi gần đây, đồng LME | test view roundtrip + LME parser; review độc lập 12 điểm đã sửa | done — chờ UAT | 2026-10-06 | Nhập tay + AI đã bỏ theo D11; Actions chưa chạy (chưa push) |
| 3 | Tác động BĐS (mới), bộ ngưỡng đặt tên, form ngưỡng 5 bước tự lưu, scorecard Nhà ở / KCN theo trụ cột | pytest 134 pass; rescore khớp build; test mở form không tự lưu (bắt lỗi lưu lặp ngưỡng Fed); backtest 10 năm | done — chờ duyệt ngưỡng | 2026-10-06 | 07/10: Scorecard thay hẳn trang Tác động BĐS (đã xóa cả 2 bản + code riêng); menu gom 2 nhóm Theo dõi · Cấu hình |
| 4 | Scorecard v2: logic đo mới (TB trượt, tổng 12 tháng, ngưỡng cứng hai phía), bộ Theo dõi BĐS - 01, trang Cấu hình scorecard, màu ô tác động | pytest 155 pass; backtest 2021, 2022–23; AppTest sửa mốc → nháp, Lưu → ghi | done — chờ UAT | 2026-10-06 | Kế hoạch: docs/plan_scorecard_v2.md |

**Project status:** in-progress
