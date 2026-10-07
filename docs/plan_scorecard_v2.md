# Kế hoạch scorecard v2 (06/10/2026) — đã làm đợt 1–3, chờ UAT

> Khác kế hoạch: trụ cột **chia đều** (người dùng chọn, không dùng 30/30/20/10/10). Tín dụng − M2 bỏ vì dữ liệu M2 lỗi từ 10/2025; liên NH chuyển sang trụ cột Tín dụng và thanh khoản. Mốc chỉnh theo dữ liệu: LS huy động 4,75/5,5/6,25/7; liên NH 2/3/4/5; FDI −25/−10/10/25; đồng −15/−5/10/25; Brent −20/−5/15/40. Dải xếp hạng: 0,8 / 0,45 / 0,05 / −0,2.

## 0. Hiện trạng và vấn đề

- 3 bộ mẫu hiện tại được làm vội: mốc chọn tay, trọng số chia đều, một số chỉ số đo sai cách.
  - Tín dụng đang chấm một phía, nên tăng quá nóng không bị trừ điểm.
  - FDI và đầu tư công dùng số lũy kế từ đầu năm, bị reset mỗi tháng 1.
  - Lãi liên ngân hàng chấm theo giá trị một ngày, nên dính gai Tết.
- Form cấu hình nằm dưới dashboard, rất dài, nhiều lỗi logic (mục C).

## A. Bộ cấu hình "Theo dõi BĐS - 01" (thay cả 3 bộ mẫu)

Nguồn căn cứ:
- NHNN: Chỉ thị 01/2026, chỉ tiêu tín dụng 2026 là 15%; trần lãi qua đêm 6% sau 9/2022.
- Mục tiêu 2026 (file mục tiêu 28.1): GDP 10% (2025: 8%), CPI bình quân 4,5%, tín dụng 15%.
- IMF Article IV 2024; báo cáo VBMA 2023; CBRE và Savills về KCN; các bài theinvestor, VNS, VIR (link đầy đủ ở mục F).

Mốc ghi [NĐ] là nhận định, chưa có nguồn trực tiếp. Mốc [NĐ] sẽ được kiểm lại theo phân vị lịch sử của chính chuỗi trong app trước khi chốt.

Toàn bộ dùng **ngưỡng cứng**, 5 mức (+2 … −2). Riêng tín dụng dùng ngưỡng cứng hai phía (mục B1).

### A1. Nhà ở — 10 chỉ số

Trọng số trụ cột: Chi phí vốn 30 · Tín dụng & thanh khoản 30 · Cầu & thu nhập 20 · Ổn định vĩ mô 10 · Hạ tầng 10.

| Trụ cột | Chỉ số (mã) | Đo | Chiều | Mốc 1–4 | Căn cứ |
|---|---|---|---|---|---|
| Chi phí vốn | LS huy động 12T Big4 (`deposit_12m_big4`) | giá trị | tăng là xấu | 4,5 / 5,5 / 6,5 / 7,5 | [NĐ]; P10 ≈ 4,7, P90 ≈ 6,8 trong 10 năm |
| | Liên NH qua đêm (`interbank_on`) | **TB 20 ngày** | tăng là xấu | 3 / 4,5 / 6 / 8 | Trần 6% của NHNN; TB 10/2022 là 5,8%; tránh gai Tết (phiên 17% ngày 3/2/2026) |
| | TPCP 10 năm (`govbond_10y`) | thay đổi 12 tháng (điểm %) | tăng là xấu | −0,5 / 0 / +0,5 / +1 | [NĐ]; chuỗi có xu hướng nên chấm theo thay đổi |
| Tín dụng & thanh khoản | Tín dụng so cùng kỳ (`credit_yoy`) | giá trị | **hai phía** | 8 / 11 / 15 / 18 | Chỉ tiêu 15%; 2025 tăng 19,1%, tín dụng/GDP 145% (Fitch); vùng 11–15 tốt nhất |
| | Tín dụng − M2 (`credit_minus_m2`) | giá trị | tăng là xấu | −2 / 0 / 2 / 4 | [NĐ]; tín dụng chạy nhanh hơn huy động là áp lực thanh khoản |
| Cầu & thu nhập | GDP công bố (`gdp_yoy_published`) | giá trị | tăng là tốt | 5 / 6 / 7 / 8 | Mục tiêu 2025 là 8%, 2026 là 10%: trên 8 đã là Rất tốt |
| Ổn định vĩ mô | CPI so cùng kỳ (`cpi_yoy`) | giá trị | tăng là xấu | 2,5 / 3,5 / 4,5 / 5,5 | Mục tiêu khoảng 4,5 |
| | CPI nhà ở & VLXD (`cpi_housing_yoy`) | giá trị | tăng là xấu | 3 / 5 / 7 / 9 | [NĐ]; 2023 dao động 5–8% |
| | Tỷ giá trung tâm (`fx_central`) | % so cùng kỳ | tăng là xấu | 1 / 2 / 3 / 5 | [NĐ]; biên độ ±5% |
| Hạ tầng | Đầu tư công (`public_investment`) | **tổng 12 tháng trượt, % so cùng kỳ** | tăng là tốt | 0 / 10 / 20 / 30 | [NĐ]; bỏ số lũy kế từ đầu năm (nhiễu tháng 1–2) |

### A2. KCN — 10 chỉ số

Trọng số trụ cột: FDI & cầu thuê 35 · Sản xuất & thương mại 30 · Chi phí vốn & rủi ro 20 · Chi phí đầu vào 15.

| Trụ cột | Chỉ số (mã) | Đo | Chiều | Mốc 1–4 | Căn cứ |
|---|---|---|---|---|---|
| FDI & cầu thuê | FDI đăng ký (từ `fdi_registered_ytd`) | **tổng 12 tháng trượt, % so cùng kỳ** | tăng là tốt | −20 / −5 / 5 / 20 | [NĐ]; dẫn trước 6–18 tháng; 2025 đạt 38,4 tỷ USD (+0,5%) |
| Sản xuất & thương mại | PMI (`pmi_vn`) | giá trị | tăng là tốt | 47 / 49 / 50 / 52 | 50 là ranh giới; 4/2025 xuống 45,6 khi Mỹ công bố thuế |
| | Xuất khẩu (`export_yoy`) | **TB 3 tháng** | tăng là tốt | 0 / 5 / 10 / 15 | [NĐ] |
| | GDP công bố (`gdp_yoy_published`) | giá trị | tăng là tốt | 5 / 6 / 7 / 8 | Mục tiêu 2026 |
| Chi phí vốn & rủi ro | LS huy động 12T Big4 | giá trị | tăng là xấu | như Nhà ở | Dùng chung một cách chấm |
| | TPCP 10 năm | thay đổi 12 tháng | tăng là xấu | như Nhà ở | |
| | DXY (`dxy`) | % so cùng kỳ | tăng là xấu | −5 / 0 / 5 / 10 | [NĐ]; USD mạnh hút vốn khỏi thị trường mới nổi |
| | VIX (`vix`) | **TB 1 tháng** | tăng là xấu | 15 / 20 / 25 / 30 | Ngưỡng thị trường thường dùng |
| Chi phí đầu vào | Đồng LME (`copper`) | % so cùng kỳ | tăng là xấu | −10 / 0 / 10 / 25 | [NĐ] |
| | Dầu Brent (`brent`) | % so cùng kỳ | tăng là xấu | −10 / 0 / 10 / 25 | [NĐ] |

Bỏ khỏi scorecard:
- Spread HY Mỹ: chỉ có từ 10/2023, quá ngắn để kiểm.
- UST 10 năm: tác động đã đi qua tỷ giá và DXY, giữ thì tính hai lần.
- Đầu tư công ở KCN: tránh tính hai lần, có thể thêm lại nếu muốn.

### A3. Kiểm chứng trước khi trình

- Backtest 10 năm:
  - Cuối 2022–2023 phải ra Bất lợi hoặc Rất bất lợi. Dự kiến bật sớm nhờ lãi liên NH và TPCP (tháng 9–10/2022).
  - 2021 ở KCN phải ra Bất lợi: PMI, xuất khẩu, GDP quý 3/2021.
- Hiệu chỉnh lại dải xếp hạng theo lịch sử của bộ mới.
- Ghi rõ những gì scorecard **không** bắt được: kênh trái phiếu doanh nghiệp (chưa có dữ liệu), tín dụng BĐS riêng.

## B. Logic cần bổ sung (để làm được mục A)

| # | Việc | Vì sao |
|---|---|---|
| B1 | Ngưỡng cứng **hai phía**: vùng giữa [mốc 2, mốc 3] là tốt nhất, càng ra xa càng xấu | Tín dụng tăng quá nhanh cũng là rủi ro (2021, 2025) |
| B2 | Cách đo mới: **trung bình N ngày/tháng** và **tổng 12 tháng trượt, % so cùng kỳ** | Tránh gai thanh khoản; tránh reset từ đầu năm và các dự án FDI lớn đột biến |
| B3 | **Trọng số theo trụ cột** đặt trong file phân khúc; trong trụ cột chia đều | Khủng hoảng 2022–23 đến từ chi phí vốn và trái phiếu, trụ cột tài chính cần nặng hơn |
| B4 | Dòng mới thêm vào mặc định là ngưỡng cứng, mốc gợi ý từ P10/30/70/90 làm tròn | Thống nhất với cách dùng ngưỡng cứng |
| B5 | FDI: tách số tháng từ số lũy kế rồi cộng 12 tháng | Số liệu gốc là lũy kế YTD |

## C. Cấu hình — review lại logic và giao diện

### C1. Lỗi logic đang có

1. Đổi kiểu, chiều, cách đo hoặc số mức thì **mốc đã nhập bị thay bằng mốc gợi ý**, không báo gì.
2. Chọn "Ngưỡng cứng" vẫn hiện 4 chiều, trong đó 2 chiều không hợp lệ: chọn xong mới báo lỗi.
3. "Lệch mục tiêu CP" hiện với cả chỉ số không có mục tiêu.
4. Thêm dòng mới thì mặc định là phân vị 5 năm, ngược với cách dùng ngưỡng cứng.
5. Trụ cột nhập chữ tự do: gõ sai một chữ là thành trụ cột mới, trọng số lệch.
6. Ô trọng số để trống hay ghi số rất khó hiểu; không thấy trọng số thực tế (%).
7. Mốc hiện "4.5" (dấu chấm) nhưng khoảng ghi "4,5"; không có đơn vị.
8. Dòng chữ "1826 điểm trong 5 năm" hiện cả khi ngưỡng cứng không dùng cửa sổ năm.

### C2. Lỗi giao diện đang có

1. Cấu hình nằm dưới dashboard: trang rất dài, nút Lưu ở xa chỗ đang sửa.
2. Phải chọn từng dòng mới xem được ngưỡng; không có bảng tổng xem hết các dòng.
3. Form dàn 5 bước theo chiều dọc. Nhãn mức là ô nhập to; điểm ở cột xa bên phải, hiện "2.00".
4. "Nhìn lại" và biểu đồ nằm dưới mô tả, cách xa ô nhập mốc.

### C3. Thiết kế mới

Tách thành trang riêng **"Cấu hình scorecard"**, chỉ hiện ở chế độ quản trị. Trang Scorecard chỉ để xem.

```
┌ Bộ: [Theo dõi BĐS - 01 ▼]  Phân khúc: (Nhà ở)(KCN)(+)   Điểm nháp +0,42 Trung tính (đã lưu +0,51)
│                                    ● 2 thay đổi chưa lưu   [Lưu] [Bỏ thay đổi] [Lưu thành bộ mới…]
├──────────────────────────────────────────┬──────────────────────────────────────────────┤
│ Bảng chỉ số (bấm 1 dòng để sửa)          │ Sửa: Liên NH qua đêm                          │
│ Trụ cột · trọng số trụ cột [30%]         │ Đo     [TB 20 ngày ▼]                         │
│  Chỉ số        Đo        Mốc        Mức  │ Ngưỡng [Cứng ▼]  Chiều (Tăng là xấu|Tăng là tốt)│
│  LS huy động   giá trị   4,5…7,5   ● TT  │ Số mức (3|4|5)                                 │
│ >Liên NH ON    TB 20N    3…8       ● Tốt │ Mốc %  [3] [4,5] [6] [8]                       │
│  TPCP 10N      Δ12T      −0,5…1    ● Xấu │ ▕██ Rất tốt ██ Tốt ██ TT ██ Xấu ██ Rất xấu▏ ▲ hiện tại 3,9 │
│ Tín dụng [30%] ...                       │ [Biểu đồ 5 năm + dải màu]  1|3|5|10 năm        │
│ [+ Thêm chỉ số ▼]  [Xóa dòng]            │ 5 năm qua: Rất tốt 22% · Tốt 31% · …           │
│                                          │ ▸ Nâng cao: tên mức, điểm từng mức, mô tả      │
└──────────────────────────────────────────┴──────────────────────────────────────────────┘
```

- Chỉ hiện các lựa chọn hợp lệ theo kiểu đã chọn: ngưỡng cứng có "Tăng là tốt / Tăng là xấu / Ở giữa là tốt".
- Đổi kiểu hoặc cách đo mà mốc cũ không còn hợp → **hỏi** "Dùng mốc gợi ý?", không tự thay.
- Trụ cột chọn từ danh sách; tạo trụ cột mới bằng nút riêng; nhập trọng số theo trụ cột; hiện trọng số thực tế của từng dòng.
- Số hiển thị kiểu Việt Nam (4,5), có đơn vị.
- Thanh lưu luôn ở đầu trang, có điểm nháp so với điểm đã lưu.

## D. Thứ tự làm và cách kiểm

| Đợt | Nội dung | Kiểm |
|---|---|---|
| 1 | B1–B5 (logic + test) | Unit test mỗi cách đo mới, ngưỡng hai phía; rescore khớp build |
| 2 | Bộ "Theo dõi BĐS - 01" (mục A) + backtest + hiệu chỉnh dải xếp hạng; xóa 3 bộ mẫu | Bảng backtest 2021, 2022–23; mỗi mốc [NĐ] đối chiếu phân vị |
| 3 | Trang "Cấu hình scorecard" mới (mục C) | AppTest: thêm dòng, sửa mốc, đổi trụ cột, Lưu/Bỏ; mở trang không ghi file; ảnh 2 khổ màn hình tự xem trước khi gửi |
| 4 | Dọn: tab Tác động cũ (nếu đã duyệt), README, spec | Toàn bộ test |

Dừng trình bày: sau đợt 2 (số liệu, backtest) và sau đợt 3 (giao diện).

## E. Để sau (cần nguồn dữ liệu mới)

Theo mức độ giá trị:

1. Phát hành / đáo hạn TPDN BĐS (VBMA, HNX): tín hiệu sớm nhất của khủng hoảng 2022.
2. LS cho vay mua nhà thả nổi (tự thu thập từ 4–5 ngân hàng).
3. Tín dụng BĐS theo quý (NHNN).
4. FDI giải ngân, IIP (GSO).
5. Hấp thụ sơ cấp, lấp đầy và giá thuê KCN (CBRE/Savills/DKRA, PDF quý).
6. Kim loại và năng lượng mở rộng (nhôm, thép HRC, vàng, khí): theo kế hoạch đã gửi.

## F. Nguồn

- theinvestor.vn: credit-to-GDP 145%; lãi suất hệ thống 10/2026; thị trường TPDN 2023.
- vietnamnews.vn:
  - Tín dụng BĐS Q4/2025.
  - Liên NH 17% ngày 3/2/2026.
  - Áp lực đáo hạn TPDN BĐS 2026.
  - FDI 2025.
- baochinhphu.vn: NHNN tăng lãi suất 9 và 10/2022.
- VBMA Bond Market Report 2023.
- IMF Article IV Vietnam 2024.
- VIR và VietnamPlus: lấp đầy, giá thuê KCN.
- fibre2fashion: PMI 4/2025.
