# Scorecard v3: làm lại tab Scorecard và Cấu hình scorecard

> Trạng thái: **đã làm đợt A, D, C, B (09/10/2026), chờ UAT**; đợt E (deploy) chờ bạn đẩy code. Quyết định đã ghi vào `docs/spec.md` D15–D17.
> Bản mẫu tương tác: [prototype/scorecard_v3.html](prototype/scorecard_v3.html) (mở bằng trình duyệt; số minh họa, chỉ phân khúc Nhà ở; vòng tròn xanh ①–㉑ là chú thích).
> Căn cứ: ảnh chụp app 09/10/2026, code `metrics/scorecard.py`, `ui/scorecard_view.py`, `app_pages/scorecard*.py`, review độc lập của Codex, các quyết định trong hội thoại.

## 1. Lỗi hiện tại đã kiểm chứng

| # | Lỗi | Loại | Chỗ |
|---|---|---|---|
| 1 | Cột "Thực tế" gắn `%` cho mọi phép đo: VIX trung bình hiện "15,9%", thay đổi TPCP hiện "1,2%" (phải là điểm %) | Sai đơn vị | `scorecard_view._value_cell` |
| 2 | Đóng góp trụ cột cộng ra +0,23, điểm tổng +0,32. Công thức điểm **đúng** (chia độ phủ 73,3%); phần đóng góp hiển thị chưa chia | Trình bày | `metrics/scorecard.py:171` |
| 3 | Nút "Sửa cấu hình" không mang theo bộ/phân khúc đang xem | Luồng | `scorecard.py:56`, `scorecard_config.py:65` |
| 4 | "Ngưỡng chờ duyệt" chỉ ở chú thích cuối trang | Dễ hiểu sai | `scorecard.py:108` |
| 5 | Trang cấu hình: dòng đang sửa không được đánh dấu, tên bị cắt, mốc nhập dạng chuỗi `a; b; c` | UX | `scorecard_config.py:246` |
| 6 | Cột "Xu hướng" thực ra là chênh so kế hoạch; GDP quý đặt cạnh mục tiêu cả năm | Dễ hiểu sai | `_plan_cells` |
| 7 | Lịch sử điểm tính lại theo cấu hình hiện tại, chưa trừ độ trễ công bố, nhưng không ghi chú | Dễ hiểu sai | `metrics/scorecard.py:5` |

## 2. Quyết định đã chốt

| # | Quyết định |
|---|---|
| C1 | Bảng chỉ số hiện đủ, **không** có tab lọc; **bỏ** box FedWatch riêng (kỳ vọng FedWatch vẫn hiện ở dòng EFFR) |
| C2 | Bảng gọn: dưới tên chỉ số chỉ ghi "Cập nhật <ngày>", **không ghi nguồn**; cách đo, lý do không tính, khoảng cách tới mức xấu hơn đưa vào tooltip |
| C3 | Cột "Mốc so sánh" đổi tên **"Thông tin tham khảo"**, ô ghi số + một chữ (Mục tiêu / Kỳ vọng / Kế hoạch) |
| C4 | Cột trọng số và đóng góp **ẩn mặc định**, có nút hiện |
| C5 | **Kỳ so sánh chọn được**: tháng trước / 3 tháng trước / cùng kỳ năm ngoái; áp cho hero, thẻ "Vì sao" và cột so sánh |
| C6 | Điểm tổng hiển thị bằng **gauge** bán nguyệt 5 dải |
| C7 | Cấu hình theo flow **danh sách bộ → 4 bước**: (1) thông tin, (2) nhóm, chỉ số, tỷ trọng, (3) mốc từng chỉ số, (4) xem lại và lưu. Tạo mới trống hoặc nhân bản |
| C8 | Tỷ trọng **mặc định chia đều** (nhóm bằng nhau, chỉ số trong nhóm bằng nhau), **ghi đè được** ở từng cấp; ô trống tự chia phần còn lại |
| C9 | **Sửa online bằng mật khẩu chung** `CONFIG_PASSWORD`: ai có mật khẩu bấm Cấu hình là sửa và lưu được. Không đăng nhập Google, không danh sách email |
| C10 | Mọi người dùng **chung một kho** cấu hình trên **Google Sheets** (tab `versions`). Đã tạo và kết nối thành công 09/10/2026 (`scripts/check_gsheets.py`) |
| C11 | `CONFIG_PASSWORD` chỉ mở trang Cấu hình; `ADMIN_PASSWORD` (số Yahoo/LME, refresh, gộp inbox) chỉ dùng local. Bản online không đặt `APP_MODE=admin` |

C9–C10 **thay đổi quyết định D1 của spec** ("bản deploy chỉ đọc"): cấu hình scorecard được ghi từ bản online; số liệu vẫn chỉ đọc. Cần cập nhật `docs/spec.md` khi bắt đầu làm.

## 3. Logic

Công thức điểm giữ nguyên: `điểm = Σ(điểm mức × trọng số) ÷ độ phủ`.

| Mã | Nội dung | Đổi điểm? |
|---|---|---|
| L1 | Đóng góp chuẩn hóa = điểm × trọng số ÷ độ phủ; tổng đóng góp = điểm tổng đúng từng số lẻ | Không |
| L2 | Đơn vị theo cách đo: `level`/`mean` giữ đơn vị gốc; `pct_change`, `ytd_pct`, `sum12_pct` là `%`; thay đổi của chỉ số đo bằng % là `điểm %` | Không |
| L3 | Độ nhạy số cũ: điểm nếu các chỉ số số cũ giữ mức cuối đã biết, và biên độ khi chúng về −2 hoặc +2 (Nhà ở: +0,10 trong −0,30 … +0,77) | Không, chỉ hiển thị thêm |
| L4 | Đổi mức theo kỳ chọn + "vì sao điểm đổi" = chênh đóng góp từng nhóm (cộng đúng bằng chênh điểm), lấy từ `_row_history` | Không |
| L5 | Mức nhóm = làm tròn trung bình có trọng số của các chỉ số đang tính | Không |
| L6 | Thông tin tham khảo ghi loại và kỳ; chỉ hiện chênh khi cùng cơ sở so sánh | Không |
| L7 | Khoảng cách tới mức xấu hơn (tooltip) | Không |
| L8 | **Tỷ trọng ghi đè (C8)**: nhóm có `weight` thì giữ, nhóm trống chia đều phần còn lại; tương tự trong nhóm; tổng phải đủ 100% | **Có**, chỉ khi có ô được nhập. Hàm `weights()` hiện tại chỉ hỗ trợ trọng số từng dòng và lấp ô trống bằng **trung bình** các ô đã nhập, khác prototype, phải sửa. Bộ đang dùng chưa nhập ô nào nên điểm không đổi; khóa bằng golden test |

## 4. Giao diện

Chi tiết xem prototype; tóm tắt:

- **Scorecard**: thanh chọn (bộ, phân khúc, kỳ so sánh, ⚙ Sửa) → hero 3 thẻ (gauge + điểm + mức + badge ngưỡng; "Vì sao" đóng góp từng nhóm; "Độ tin cậy" độ phủ, số cũ, L3) → bảng theo nhóm (thu gọn được) → dòng tổng → lịch sử điểm 5 dải.
- **Cấu hình**: danh sách bộ (Tạo mới / Sửa / Nhân bản, trạng thái) → 4 bước có dấu ✓/! → thanh dưới cùng: điểm trước → sau, dòng đổi mức, Bỏ thay đổi / Quay lại / Tiếp / Lưu.
- Từ Scorecard: ⚙ mở bước 2 của đúng bộ; ✎ trên dòng mở bước 3 đúng chỉ số. Scorecard luôn hiển thị bản đã lưu, có bản nháp chưa lưu thì báo.

## 5. Lưu cấu hình online (C9–C10)

- Tab `versions`: `bo_id | version | status | payload (JSON của bộ) | saved_by | saved_at | approved_by | approved_at`. Mỗi lần lưu **thêm một dòng** (gspread `append_row`), không ghi đè cả tab.
- Đọc: phiên bản mới nhất của mỗi bộ; `st.cache_data(ttl ngắn)` có số phiên bản trong tham số.
- Chống ghi đè: lưu kèm số phiên bản đang sửa; nếu trên Sheet đã có số lớn hơn thì báo "cấu hình đã đổi, tải lại", không lưu.
- Vì mật khẩu dùng chung: xem lịch sử và **hoàn tác** về phiên bản cũ; khóa tạm sau nhiều lần nhập sai; giới hạn số lần lưu mỗi giờ và kích thước nội dung; ghi tên người lưu; không in mật khẩu, khóa hay thông báo lỗi kết nối gốc ra log.
- **Escape mọi chuỗi người dùng nhập** (tên bộ, tên nhóm, mô tả) trước khi đưa vào `st.html`, vì ai có mật khẩu cũng ghi được và người xem là bất kỳ ai.
- Dự phòng: Sheet lỗi hoặc trống thì đọc YAML trong `config/profiles/` (bản gốc trong repo).
- Trang Tổng quan và build đang đọc bộ mặc định từ YAML: phải đổi sang đọc qua cùng kho.
- Các option đã cân nhắc (Drive, repo GitHub riêng, Postgres): Sheets chọn vì nhanh, team xem được. Số người sửa tăng nhiều thì chuyển Postgres, giữ nguyên cấu trúc bảng.

## 6. Review prototype và tài liệu (09/10/2026)

Đã xem ảnh thật các màn (sáng, tối, 390px) và đối chiếu code.

| # | Vấn đề | Mức | Xử lý |
|---|---|---|---|
| R1 | Proposal cũ tự mâu thuẫn: còn ghi `st.login`, danh sách email, "giữ D1 sửa local", form 3 bước cũ | Cao | Viết lại bản này |
| R2 | Hàm tỷ trọng ở backend khác cách prototype chia (L8) | Cao | Đợt A2, có golden test |
| R3 | Prototype chỉ có một phân khúc; bộ thật có nhiều phân khúc (Nhà ở, KCN), mỗi phân khúc nhóm và chỉ số riêng | Cao | Bước 2–3 thêm chọn phân khúc; bước 1 thêm/xóa phân khúc |
| R4 | Bước **Duyệt** vô nghĩa khi ai có mật khẩu cũng sửa được | Trung bình | Câu hỏi Q2 |
| R5 | Gauge vẽ thang −1 … 1,2 nhưng chữ ghi "thang −2 … +2"; điểm +2 bị ghim ở đầu mút | Trung bình | Q3; ghi rõ đầu mút "≤ −1", "≥ 1,2" |
| R6 | Gauge sáng: dải Bất lợi (cam) và Trung tính (vàng sẫm) khó phân biệt | Thấp | Đổi màu dải Trung tính khi dựng bằng Plotly |
| R7 | Thanh tỷ trọng ở bước 2 dùng màu trạng thái (xanh, cam) cho từng nhóm, trái quy tắc màu | Thấp | Dùng bảng màu phân loại `CATEGORICAL` của app |
| R8 | Mở sửa một bộ khi đang có bản nháp bộ khác thì bản nháp bị bỏ không báo | Trung bình | Hỏi "bỏ bản nháp?" trước khi chuyển |
| R9 | Dòng nhóm ở cột so sánh ghi "điểm", dòng chỉ số ghi "bậc" | Thấp | Dòng nhóm ghi chênh đóng góp kèm chữ "đóng góp" |
| R10 | Bước 3: mọi dòng đều có chip "✓ Đã cấu hình", nhiều màu xanh thừa | Thấp | Chỉ hiện chip với dòng chưa xác nhận |
| R11 | 390px: bảng tràn ngang | Thấp | Streamlit tự xếp; ẩn cột Diễn biến khi hẹp |

## 7. Quyết định bổ sung (chốt 09/10/2026)

| # | Quyết định |
|---|---|
| Q1 | Hiện độ nhạy số cũ (L3) ở thẻ Độ tin cậy |
| Q2 | **Bỏ bước Duyệt**; thay bằng lịch sử phiên bản + hoàn tác; badge "Cập nhật <ngày> bởi <tên>" |
| Q3 | Gauge phóng to −1 … 1,2, hai đầu ghi "≤ −1", "≥ 1,2" |
| Q4 | Cho nhập tỷ trọng ghi đè (L8), chấp nhận đổi điểm khi có ô được nhập |
| Q5 | Bộ mặc định của trang Tổng quan chọn trong danh sách bộ ("Đặt làm mặc định", cần mật khẩu), lưu cùng kho |
| Q6 | Thanh lưu dính đáy (CSS tùy biến, kiểm sáng/tối) |
| Q7 | Làm liền A → D → C → B → E, không dừng giữa chừng; test kỹ rồi báo UAT |

## 8. Kế hoạch nâng cấp

| Đợt | Việc | File chính | Ước lượng | Dừng xem? |
|---|---|---|---|---|
| A | **Sửa lỗi gây hiểu sai trên app hiện tại**: đơn vị (L2), đóng góp chuẩn hóa (L1), truyền ngữ cảnh khi bấm sửa, ghi chú lịch sử; **A2**: hàm tỷ trọng mới (L8) + golden test điểm hiện tại không đổi | `metrics/scorecard.py`, `ui/scorecard_view.py`, `app_pages/scorecard.py`, `tests/test_scorecard.py` | 1–1,5 giờ | Không (test số tự kiểm) |
| D | **Kho cấu hình online**: `config_store` (đọc/ghi Sheet, chống ghi đè, lịch sử, hoàn tác, dự phòng YAML), cổng `CONFIG_PASSWORD` (khóa khi sai nhiều), Tổng quan đọc qua kho; test bằng kho giả, thử ghi thật 1 dòng vào Sheet | `src/macro_app/config_store.py` (mới), `ui/sidebar.py`, `profiles.py`, `tests/test_config_store.py` | 2–3 giờ | Không |
| C | **Trang Cấu hình mới**: danh sách bộ, 4 bước, nhiều phân khúc, tỷ trọng ghi đè, ô mốc riêng, xác nhận mốc, thanh lưu, escape chuỗi | `app_pages/scorecard_config.py`, `ui/rule_editor.py` | 3–4 giờ | **Có**: chụp màn, bạn xem |
| B | **Trang Scorecard mới**: gauge (Plotly), hero 3 thẻ, kỳ so sánh, bảng gọn, ẩn trọng số, L3–L5, lịch sử 5 dải | `ui/scorecard_view.py`, `app_pages/scorecard.py`, `metrics/scorecard.py` | 2–3 giờ | **Có**: chụp màn, bạn xem |
| E | **Deploy Streamlit Cloud**: Secrets (`CONFIG_PASSWORD`, `[gsheets]`), kiểm thử khói online, cập nhật spec và README | `docs/spec.md`, `README.md` | 30 phút | Không |

Thứ tự: **A → D → C → B → E**. A sửa sai số trước; D làm kho mà C cần; C và B là hai lần dừng để bạn xem giao diện.

## 9. Rủi ro và giả định

- Prototype dùng số minh họa; lịch sử, kỳ so sánh và vài mốc (Hạ tầng, tín dụng hai phía) là giả định. Chưa dựng KCN.
- Streamlit không có sẵn danh sách chọn dòng và thanh dính đáy như prototype; đợt C có thể phải dùng `st.button` theo hàng hoặc CSS (Q6). Bố cục có thể lệch nhẹ so với prototype.
- Google Sheets không có giao dịch: chống ghi đè dựa vào số phiên bản, đủ cho vài người sửa cùng lúc, không tuyệt đối.
- Mật khẩu dùng chung lộ ra là ai cũng sửa được; giảm thiệt hại bằng lịch sử + hoàn tác và đổi mật khẩu trong Secrets.
