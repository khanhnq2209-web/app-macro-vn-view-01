# Đề xuất nâng cấp các màn còn lại (sau Scorecard v3)

> Trạng thái: **đề xuất, chờ chọn**. Review ngày 09/10/2026 trên app chạy thật (ảnh ở `docs/screenshots/v3/`).
> Phạm vi: Tổng quan, Kế hoạch & dự báo, Quốc tế, Việt Nam, Chi tiết chỉ số, Ngưỡng, Tùy chỉnh hiển thị.

## 1. Vấn đề lớn nhất: hai hệ chấm song song

| | Hệ "Ngưỡng" (cũ) | Hệ Scorecard (v3) |
|---|---|---|
| Dùng ở | Tổng quan, Chi tiết, bảng "Số liệu mới nhất" ở Quốc tế / Việt Nam | Scorecard, Cấu hình, báo cáo PDF/Word |
| Mức | Đỏ · Cam · Vàng · Xanh · Xanh đậm | Rất tốt … Rất xấu (+2 … −2) |
| Ngưỡng | Bộ ngưỡng riêng; **38/57 chỉ số còn dùng z-score mặc định** | Mốc cứng theo từng bộ, đã có căn cứ |
| Ví dụ | LS huy động 12T Big4 5,90% = **Cam** | cùng số = **Trung tính** |

Người xem thấy hai kết luận khác nhau cho cùng một con số. Đề xuất (cần bạn chốt, **Q1**):

- **A. Một nguồn chân lý = mốc của Scorecard (khuyến nghị).** Chỉ số nằm trong bộ mặc định thì Tổng quan và Chi tiết hiện đúng mức của bộ đó (cùng chữ, cùng màu với Scorecard). Chỉ số chưa thuộc bộ nào thì hiện "Chưa có ngưỡng nghiệp vụ", kèm vị trí thống kê (z-score) làm tham khảo, không tô màu cảnh báo. Trang **Ngưỡng** gộp vào Cấu hình scorecard, thành bước 3 của bộ.
- **B. Giữ hai hệ nhưng đổi tên rõ:** "Vị trí thống kê (so 5 năm)" khác với "Mức theo scorecard". Ít việc hơn, nhưng vẫn hai kết luận.

## 2. Từng màn

| Màn | Hiện trạng / vấn đề | Đề xuất | Cỡ |
|---|---|---|---|
| **Tổng quan** | Dải đếm Đỏ/Cam/Vàng theo hệ cũ; dòng cảnh báo dài; **chưa có các chỉ số mới** (WTI, khí, GPR, OVX, GDP Mỹ…); chưa thấy điểm các scorecard | Đầu trang: **thẻ tóm tắt 7 scorecard** (gauge nhỏ + điểm + mức + đổi so tháng trước, bấm vào mở Scorecard). Bảng chỉ số dùng mức theo Q1. Thêm khối "Năng lượng & địa chính trị". Nút **Tải PDF** 1 trang cho slide | M |
| **Chi tiết chỉ số** | "Trạng thái ngưỡng: Cam" khác Scorecard; bảng kỹ thuật (Z-score, Cờ) | Thẻ "**Có trong bộ nào**": mức của chỉ số trong từng bộ (vd BĐS-01: Trung tính · Lãi suất: Trung tính) + khoảng cách tới mức xấu hơn; biểu đồ có **dải mức** như trang Cấu hình; kỳ so sánh tháng / 3 tháng / năm; ẩn cột kỹ thuật vào mục "Chi tiết" | M |
| **Việt Nam** | Biểu đồ **GDP tự tính +89%, GDP ngành BĐS +72%, xây dựng +107%** (chuỗi gãy năm gốc) vẫn hiện như số thật | **Sửa dữ liệu**: tính lại tăng trưởng ngành theo cùng năm gốc, hoặc ẩn đoạn gãy + chú thích. Đến khi sửa xong, ẩn 3 chuỗi khỏi biểu đồ mặc định. Bảng "Số liệu mới nhất" đổi cột dễ đọc (bỏ Z-score, Cờ thô) | M |
| **Quốc tế** | Nhóm A2 chỉ có Brent; chưa có WTI, khí, GPR, OVX, xăng Mỹ; nhãn năm trục x bị cắt ở vài biểu đồ | Thêm nhóm **"Năng lượng"** (dầu, khí, xăng) và **"Địa chính trị & bất định"** (GPR, GEPU, OVX, VIX); sửa lề trục; cùng kiểu bảng như Scorecard | S |
| **Kế hoạch & dự báo** | Bảng sửa hiện chữ "None" ở ô trống; chỉ có mục tiêu CP và FedWatch | Ô trống để trống; thêm biểu đồ **thực tế so kế hoạch** theo tháng; thêm nguồn dự báo: giá dầu (EIA STEO), GDP (IMF WEO) | M |
| **Ngưỡng** | Kỹ thuật (z-score, N năm, phân vị); lịch sử thay đổi là chuỗi dict thô; trùng khái niệm với "bộ" scorecard | Theo Q1-A: gộp vào Cấu hình scorecard. Nếu giữ: lịch sử hiển thị "mốc cũ → mốc mới" dạng bảng, ẩn kiểu ngưỡng thống kê vào "Nâng cao" | S–M |
| **Tùy chỉnh hiển thị** | Lưu file YAML trên máy: **lên Streamlit Cloud sẽ mất khi app khởi động lại** (cùng vấn đề cấu hình đã giải) | Lưu vào **cùng kho Google Sheets** (tab `views`) như bộ scorecard, có lịch sử; cho người có `CONFIG_PASSWORD` sửa | S |

## 3. Dữ liệu còn thiếu / nên thêm

| Mục | Ghi chú |
|---|---|
| Tồn kho và sản lượng dầu Mỹ | Không có trên FRED; cần API EIA (đăng ký key miễn phí) |
| GDP ngành BĐS / xây dựng | Sửa cách tính tăng trưởng qua điểm đổi năm gốc (mục 2) |
| M2 | File Excel lỗi từ 10/2025; API dulieukinhte chỉ có số tuyệt đối → tự tính % từ đầu năm |
| LS tái cấp vốn | Số cũ (03/08/2026); gắn API dulieukinhte nếu có mã |

## 4. Thứ tự đề xuất

| Đợt | Việc | Ước lượng |
|---|---|---|
| F | Q1 (thống nhất hệ chấm) + Chi tiết chỉ số | 3–4 giờ |
| G | Tổng quan (thẻ 7 scorecard, khối năng lượng, PDF) + Quốc tế (nhóm mới) | 2–3 giờ |
| H | Việt Nam (sửa GDP ngành) + Kế hoạch & dự báo | 2–3 giờ |
| I | Tùy chỉnh hiển thị lưu Google Sheets; gộp/đơn giản trang Ngưỡng | 1–2 giờ |

## 5. Câu hỏi cần chốt

| # | Câu hỏi | Mặc định |
|---|---|---|
| Q1 | Thống nhất hệ chấm theo phương án A (mốc Scorecard là nguồn chân lý)? | A |
| Q2 | Tổng quan dùng bộ mặc định hay cho chọn bộ? | Bộ mặc định, có ô chọn |
| Q3 | Đăng ký API EIA để lấy tồn kho/sản lượng dầu? | Có (bạn đăng ký key, tôi nối) |
