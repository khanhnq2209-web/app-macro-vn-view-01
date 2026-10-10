"""Hướng dẫn cài bản tin BĐS hằng ngày bằng Scheduled task của ChatGPT (không cần plugin)."""

import streamlit as st

from macro_app.paths import ROOT
from macro_app.ui import components as ui

PROMPT_FILE = ROOT / "docs" / "prompts" / "Prompt_BDS_Daily_Digest_Scheduled_Task.txt"
START, END = "BẮT ĐẦU PROMPT", "KẾT THÚC PROMPT"

st.title("Bản tin BĐS hằng ngày bằng ChatGPT")
st.caption(
    "Cài một lần, ChatGPT tự tìm tin vĩ mô, pháp lý, thị trường và doanh nghiệp BĐS mỗi sáng "
    "rồi gửi bản tóm tắt vào cuộc trò chuyện của bạn. Mỗi người cài trên tài khoản của mình."
)

text = PROMPT_FILE.read_text(encoding="utf-8") if PROMPT_FILE.exists() else ""
lines = text.splitlines()
start = next((i for i, x in enumerate(lines) if START in x), None)
end = next((i for i, x in enumerate(lines) if END in x), None)
prompt = "\n".join(lines[start + 1 : end]).strip() if start is not None and end else text

st.markdown(
    """
#### 4 bước cài đặt

| Bước | Làm gì |
|---|---|
| 1 | Mở [ChatGPT](https://chatgpt.com), tạo **cuộc trò chuyện mới** (tài khoản có tính năng *Tasks / Scheduled*). |
| 2 | Bấm biểu tượng **copy** ở góc khung prompt bên dưới, dán vào ChatGPT và gửi. Có thể sửa trước: **giờ nhận** (mặc định 08:00), **địa bàn**, **phân khúc**, **doanh nghiệp ưu tiên**. |
| 3 | Chờ ChatGPT **xác nhận đã tạo task** (tên, giờ chạy, múi giờ) và chạy **bản thử**. Chưa có xác nhận thì coi như chưa tạo. |
| 4 | Kiểm tra / sửa / tắt task tại [chatgpt.com/scheduled](https://chatgpt.com/scheduled). Đọc bản thử, chưa ưng thì nhắn ChatGPT chỉnh rồi cập nhật task. |
"""
)

c1, c2 = st.columns([1, 3], vertical_alignment="center")
c1.download_button(
    "⬇ Tải file prompt (.txt)",
    text.encode("utf-8"),
    file_name=PROMPT_FILE.name,
    mime="text/plain",
    width="stretch",
    disabled=not text,
)
c2.caption("File gồm hướng dẫn và toàn bộ prompt; gửi cho đồng nghiệp để mỗi người tự cài.")

st.markdown("#### Prompt (copy nguyên khung này)")
if prompt:
    st.code(prompt, language=None, wrap_lines=True, height=420)
else:
    st.error("Không tìm thấy file prompt trong docs/prompts/.")

with st.expander("Bản tin sẽ gồm gì?"):
    st.markdown(
        """
- **Phạm vi 7 nhóm:** quốc tế · vĩ mô Việt Nam · pháp lý · thị trường BĐS (nhà ở, KCN, văn phòng,
  bán lẻ, khách sạn…) · doanh nghiệp, dự án · báo cáo nghiên cứu mới · lịch sắp tới.
- **4 mục:** tóm tắt chính · bảng tin đáng chú ý (sentiment, hàm ý, link nguồn) · phân tích 1–2 vấn đề ·
  các mốc cần theo dõi 7 ngày tới.
- **Kiểm chứng:** đọc bài gốc, phân biệt dự thảo / hiệu lực, đăng ký / giải ngân, mục tiêu / thực tế;
  chấm độ tin cậy nguồn; không bịa số để đủ khung.
"""
    )

with st.expander("Lưu ý"):
    st.markdown(
        """
- Task chạy trên **tài khoản ChatGPT của bạn**; app này không gửi dữ liệu nào sang ChatGPT.
- Bản tin do AI tổng hợp từ web: dùng để **phát hiện tin**, số liệu trọng yếu vẫn đối chiếu nguồn gốc
  trước khi dùng cho báo cáo.
- Muốn đổi giờ / phạm vi: nhắn ChatGPT trong cùng cuộc trò chuyện “cập nhật task BĐS Daily Digest…”,
  tránh tạo task trùng.
"""
    )

ui.footer()
