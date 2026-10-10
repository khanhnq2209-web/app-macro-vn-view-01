# Nâng cấp cấu hình và dữ liệu theo Workshop BĐS nhà ở 10/2026

> Trạng thái: **đề xuất, chưa làm** (10/10/2026). Nguồn: `Workshop BĐS 10.2026.pdf` (40 trang).

## 1. Workshop nói gì mà app chưa có

| Workshop (trang) | Thông tin | App hiện tại |
|---|---|---|
| Chu kỳ BĐS (3–4) | Nhà ở đang **Bão hòa**, có nguy cơ sang **Suy thoái** nếu lãi suất neo cao 1–2 năm. Khung: vĩ mô (vốn & lãi suất, lạm phát & thu nhập, pháp lý) + thị trường (cung, hấp thụ, giá) | Chỉ có điểm vĩ mô, không có chỉ số thị trường, không xếp giai đoạn chu kỳ |
| Bối cảnh vĩ mô (6) | GDP 9T 9,01%, Q3 **9,95%**; CPI bình quân 9T 4,52%; tín dụng BĐS +8,3% (6T); **lãi vay mua nhà ~10,9%** (thả nổi 15–16%); đầu tư công 62,9% kế hoạch | GDP mới tới Q2, CPI tới 8/2026 (nguồn VBMA chậm); không có tín dụng BĐS, lãi vay mua nhà |
| Lãi suất (7–11) | Chênh **LS tái cấp vốn − EFFR ≈ 0,7%** là "mỏng"; tín dụng tăng nhanh hơn M2, khoảng cách nới rộng; **tín dụng/GDP**, **LDR** cao nhất khu vực; dự trữ ≈ **2 tháng nhập khẩu**, thâm hụt thương mại; TT 50/2026 nới LDR 85→95% | Có chênh lãi liên ngân hàng − EFFR; có tín dụng, M2 nhưng chưa chấm khoảng cách; không có tín dụng/GDP, LDR, dự trữ, cán cân thương mại |
| Vốn chủ đầu tư (12) | TPDN BĐS **đáo hạn 12 tháng** tới, phát hành theo tập đoàn và lãi suất | Không có |
| Khả năng chi trả (13) | Giá nhà/thu nhập (Numbeo) mở rộng; so sánh kênh đầu tư: vàng SJC, USD VCB, VN-Index, tiết kiệm 12T | Có USD VCB, tiết kiệm; thiếu vàng SJC, VN-Index, giá nhà/thu nhập |
| Pháp lý (14–15) | Mốc luật 2024–2026, NQ 171, NQ 21-NQ/TW, Luật Phát triển đô thị 18/2026 (hiệu lực 1/10/2026) | Không có (AI digest phủ tin) |
| Thị trường (17–21) | Bộ Xây dựng: dự án cấp phép mới / đủ điều kiện bán / hoàn thành theo quý; cung–tiêu thụ HN, HCM; giá thứ cấp; hấp thụ theo phân khúc | Không có. Số CBRE/Savills là dữ liệu mua, **không đưa vào bản công khai** (trang 34) |
| Rủi ro (30) | 3 lớp: nhất thời (giá dầu, chi phí xây dựng) · chu kỳ 1–3 năm (lãi suất, tỷ giá, vật liệu, nhân công) · hệ thống (pháp lý, thị trường & phân khúc, quy hoạch) | Scorecard phủ lớp chu kỳ; chưa gắn với rủi ro |

## 2. Dữ liệu nên thu thập thêm

| # | Chỉ số | Nguồn | Cách lấy | Dùng để |
|---|---|---|---|---|
| D1 | GDP, CPI cập nhật kịp | Cục Thống kê qua API dulieukinhte | Gắn mã API (như đã làm cho TPCP, liên NH) | Sửa độ trễ: GDP Q3, CPI tháng 9 |
| D2 | Cán cân thương mại tháng | Hải quan (file `18_XNK.xlsx` có sẵn) hoặc API | Tự động | Chấm ở Tỷ giá (nghiên cứu EMP đã đề xuất) |
| D3 | Tín dụng/GDP; tăng trưởng tín dụng − M2 | Tính từ dư nợ, M2, GDP danh nghĩa 4 quý (`GDP-hien-hanh.xlsx` có sẵn) | Tự động | Chấm ở Lãi suất (áp lực thanh khoản) |
| D4 | Tín dụng BĐS (dư nợ, tăng so đầu năm) | NHNN công bố theo quý, qua báo chí | Nhập tay như FDI thực hiện | Chấm ở Nhà ở, hai chiều (nóng là sắp siết) |
| D5 | Lãi vay mua nhà bình quân (ưu đãi, thả nổi) | NHNN "lãi cho vay bình quân mới", VARS, VNBA | Nhập tay tháng | **Biến lõi** của Nhà ở |
| D6 | TPDN BĐS: phát hành, đáo hạn 12 tháng tới | VBMA, HNX, VIS Rating | Nhập tay tháng / quý | Chấm ở Nhà ở (áp lực vốn chủ đầu tư) |
| D7 | Dự trữ ngoại hối (tháng nhập khẩu) | IMF, NHNN | Nhập tay quý | Tỷ giá (khả năng chống đỡ) |
| D8 | LDR hệ thống | NHNN, báo cáo ngân hàng | Nhập tay quý | Tham khảo ở Lãi suất |
| D9 | Cung nhà ở theo quý (Bộ Xây dựng): dự án cấp phép mới, đủ điều kiện bán, giao dịch | Báo cáo quý của Bộ Xây dựng (công khai) | Nhập tay quý | Chỉ số thị trường cho khung chu kỳ |
| D10 | Vàng SJC, VN-Index | Yahoo / SJC | Tự động | Biểu đồ "so sánh kênh đầu tư" (chỉ hiển thị) |
| D11 | Giá nhà / thu nhập HN, HCM | Numbeo (năm) | Nhập tay | Chỉ hiển thị |

Nhập tay: dùng cơ chế `manual_inputs.csv` + agent tra cứu có link nguồn như FDI thực hiện.

## 3. Nâng cấp cấu hình

| # | Bộ / tab | Thay đổi | Lý do (workshop) |
|---|---|---|---|
| C1 | Nhà ở | Thêm nhóm **"Nguồn vốn BĐS"**: lãi vay mua nhà (D5, mức), tín dụng BĐS (D4, hai chiều), TPDN BĐS đáo hạn 12T (D6) | Workshop coi lãi vay mua nhà và vốn chủ đầu tư là kênh chính (trang 6, 7, 12). Hiện chỉ có lãi huy động làm đại diện |
| C2 | Nhà ở | Thêm nhóm **"Thị trường"** (khi có D9): giao dịch, cung mới theo quý | Khung chu kỳ cần cả vĩ mô và thị trường (trang 4) |
| C3 | Lãi suất | Chấm **tín dụng − M2** (D3); LDR tham khảo | Trang 10–11: khoảng cách nới rộng = áp lực lãi suất |
| C4 | Tỷ giá | Thêm **cán cân thương mại 3 tháng** (D2), dự trữ (D7) | Trang 10: thâm hụt thương mại + dự trữ 2 tháng nhập khẩu |
| C5 | Tỷ giá, Lãi suất | Hiện thêm **chênh LS điều hành (tái cấp vốn − EFFR)** bên cạnh chênh liên ngân hàng − EFFR | Workshop dùng chênh điều hành (≈0,7%); app chấm chênh thị trường (−0,77). Hai số khác dấu, cần cùng hiện để người đọc không bối rối |
| C6 | Nhà ở | Tham khảo: chỉ số giá vật liệu xây dựng (Cục Thống kê, quý) | Rủi ro chi phí NVL (trang 30) |

## 4. Tính năng mới (hiển thị)

| # | Tính năng | Nội dung |
|---|---|---|
| U1 | **Khung chu kỳ BĐS** trên trang Scorecard / Tổng quan | 4 ô Phục hồi · Tăng trưởng · Bão hòa · Suy thoái; vị trí xác định theo quy tắc: hướng điểm vĩ mô (3 tháng) + cung, hấp thụ, giá (D9). Nhãn [giả định] chờ QTRR |
| U2 | **So sánh kênh đầu tư** | Vàng SJC, USD VCB, VN-Index, tiết kiệm 12T, cùng gốc 100 (D10) |
| U3 | **Mốc pháp lý** | Dòng thời gian luật/nghị quyết (YAML nhập tay), trạng thái dự thảo / hiệu lực |
| U4 | **Bản đồ rủi ro** 3 lớp | Mỗi rủi ro gắn chỉ số trong app (giá dầu → tab Năng lượng; lãi suất → Lãi suất…) |

## 5. Đợt và ước lượng

| Đợt | Việc | Thời gian agent | Dừng? |
|---|---|---|---|
| G1 | D1, D2, D3, D10 (tự động) + D4, D5, D6, D7 (nhập tay có nguồn) | 2–3 giờ | Không |
| G2 | C1, C3, C4, C5 + kiểm định lịch sử + đối chiếu nhận định chuyên gia | 1–2 giờ | Có: duyệt mốc mới |
| G3 | U1, U2, U3 (+ D9 nếu chọn) | 2–3 giờ | Có: xem giao diện |

## 6. Cần chốt

| # | Câu hỏi | Mặc định |
|---|---|---|
| Q1 | Ai cập nhật số nhập tay hằng tháng / quý (D4–D9)? | Agent tra cứu khi bấm refresh, người duyệt |
| Q2 | U4 có nội dung riêng của GELEX (trang 30–31): **không đưa lên bản công khai**? | Chỉ hiện ở chế độ nội bộ |
| Q3 | Khung chu kỳ U1: dùng quy tắc đơn giản hay chờ có D9? | Làm sau khi có D9 |
