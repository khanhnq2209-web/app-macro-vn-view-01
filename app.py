"""App theo dõi vĩ mô — yếu tố tác động thị trường BĐS Việt Nam.

Chạy: streamlit run app.py   (dữ liệu: python -m macro_app.cli build | refresh)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st

from macro_app.ui import sidebar, style

st.set_page_config(page_title="App theo dõi vĩ mô", page_icon="📊", layout="wide")
sidebar.init_state()
present = sidebar.presentation_mode()
style.inject(present)

pages = {
    "Theo dõi": [
        st.Page("app_pages/scorecard.py", title="Scorecard", default=True),
        st.Page("app_pages/overview.py", title="Tổng quan"),
        st.Page("app_pages/forecasts.py", title="Kế hoạch & dự báo"),
        st.Page("app_pages/international.py", title="Quốc tế"),
        st.Page("app_pages/vietnam.py", title="Việt Nam"),
        # mở qua link tên chỉ số ở các bảng, không cần nằm trên menu
        st.Page("app_pages/detail.py", title="Chi tiết chỉ số", visibility="hidden"),
    ],
}
if sidebar.is_admin():  # trang sửa cấu hình chỉ có khi chạy local quản trị
    pages["Cấu hình"] = [
        st.Page("app_pages/scorecard_config.py", title="Cấu hình scorecard"),
        st.Page("app_pages/thresholds.py", title="Ngưỡng"),
        st.Page("app_pages/views_editor.py", title="Tùy chỉnh hiển thị"),
    ]
nav = st.navigation(pages, position="hidden" if present else "sidebar")
if not present:
    sidebar.render()
nav.run()
