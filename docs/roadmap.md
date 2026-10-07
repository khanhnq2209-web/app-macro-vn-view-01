# Đề xuất nâng cấp để app hoàn thiện (06/10/2026)

Xếp theo giá trị cho người dùng QTRR / công sức. ✅ = đã làm trong đợt này.

## Đã làm: ghép dự báo vào scorecard (D13)

- ✅ **Lãi Fed + FedWatch:**
  - Trang Chi tiết lãi Fed có đường kỳ vọng nét đứt theo các kỳ họp FOMC, kèm bảng kỳ họp (biên trên kỳ vọng, chênh so hiện tại, khoảng khả năng cao nhất và xác suất).
  - Ưu tiên số CME QuikStrike; nếu cũ hơn 7 ngày thì dùng bản tự tính từ hợp đồng ZQ.
- ✅ **Dòng scorecard có dự báo hoặc mục tiêu:**
  - Lãi Fed (nếu thêm vào phân khúc), GDP và tín dụng (mục tiêu Chính phủ năm nay): ghi "Kỳ vọng …" hoặc "Mục tiêu 2026: …" và mức tương ứng theo đúng ngưỡng của dòng.
  - Không tính vào điểm chính.
- ✅ **Điểm "nếu theo dự báo/mục tiêu" ở đầu trang (thô):** thay điểm các dòng có dự báo bằng mức của dự báo xa nhất, giữ nguyên các dòng khác.
- ✅ **Khối "Tín hiệu dự báo"** trên trang Scorecard: đường lãi Fed kỳ vọng.

## Nên làm tiếp: dự báo / kỳ vọng

| # | Việc | Vì sao | Nguồn | Công |
|---|---|---|---|---|
| F1 | Đường cong kỳ hạn TPCP VN (2, 5, 10 năm) + kỳ vọng lãi suất trong nước ngầm định | Tương đương FedWatch cho VN: thị trường đang chờ tăng hay giảm lãi | HNX/VBMA lợi suất theo kỳ hạn | M |
| F2 | Dự báo đồng thuận GDP, CPI VN (IMF WEO, World Bank, ADB) cạnh mục tiêu Chính phủ | Mục tiêu thường lạc quan hơn đồng thuận; chênh lệch là tín hiệu rủi ro | IMF WEO (2 lần/năm), WB GEP | S |
| F3 | Kỳ vọng lạm phát Mỹ (breakeven 5 năm), dot plot của Fed | Bổ sung góc Fed tự dự báo, khác giá thị trường | FRED `T5YIE`; FOMC SEP | S |
| F4 | Đường cong futures Brent và đồng (3, 6, 12 tháng) | Kỳ vọng chi phí đầu vào KCN | CME/ICE (cần nguồn có giấy phép) | M |
| F5 | Kịch bản (stress): người dùng chỉnh tay giá trị giả định từng dòng → điểm kịch bản | QTRR cần "nếu lãi huy động +1 điểm % thì sao" | Không cần dữ liệu mới | M |

## Nên làm tiếp: hoàn thiện app

| # | Việc | Vì sao | Công |
|---|---|---|---|
| A1 | **Cập nhật dữ liệu VN định kỳ** (dulieukinhte): lịch nhắc, trang "dữ liệu cũ" liệt kê chuỗi quá hạn | Nhà ở đang "Chưa đủ dữ liệu" chỉ vì file VN cũ 2–4 tháng | S |
| A2 | **Chấm theo ngày công bố (as-of)**: lưu ngày công bố từng kỳ, lịch sử chỉ dùng số đã công bố | Bỏ look-ahead ~1 tháng của GDP, CPI, PMI; backtest trung thực hơn | M |
| A3 | Kiểm tra cấu hình lúc nạp: YAML lỗi hoặc mã không có trong catalog → báo lỗi rõ trên trang, không sập | Sửa tay YAML dễ hỏng (đã gặp với dấu ":" trong mô tả) | S |
| A4 | Đối chiếu nguồn tự động: Brent FRED vs Yahoo, FDI nhảy bất thường, chuỗi lặp số → cờ trên Tổng quan | Review dữ liệu đã thấy các lỗi này bằng tay | S |
| A5 | Xuất báo cáo PDF/Excel scorecard theo tháng (điểm, từng dòng, lịch sử, ghi chú) | Gửi lãnh đạo / hội đồng rủi ro | M |
| A6 | Phân quyền khi deploy: đăng nhập, ai được sửa bộ cấu hình, nhật ký ai sửa gì | Hiện sửa chỉ khi chạy local | M |
| A7 | Hiệu chỉnh độ nhạy: backtest từng dòng (dòng nào báo trước khủng hoảng 2022–23, 2021), gợi ý trọng số | Thay trọng số chia đều bằng trọng số có căn cứ | M |
| A8 | Dữ liệu mới cho Nhà ở / KCN: TPDN BĐS, LS cho vay thả nổi, tín dụng BĐS, hấp thụ, lấp đầy KCN | Kênh khủng hoảng 2022 (trái phiếu) chưa có trong scorecard | L |
| A9 | ✅ Đã xóa tab Tác động cũ, gom menu Theo dõi · Cấu hình, ẩn Chi tiết chỉ số, dọn code chết (07/10) | | S |
| A10 | CI: chạy ruff + pytest trên GitHub Actions khi push; test giao diện bằng ảnh chụp | Giữ chất lượng khi Codex/người khác cùng sửa | S |

**Công:** S = dưới nửa ngày · M = 1–2 ngày · L = cần nguồn dữ liệu mới.

**Đề xuất thứ tự:** A1 → A3 → A4 → A2 → F5 → F2 → F1 → A5 → còn lại.
