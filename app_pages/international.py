"""Quốc tế (nhóm A) và FedWatch."""

import streamlit as st

from macro_app.ui import chart_page, sidebar
from macro_app.ui import components as ui
from macro_app.ui.fedwatch_view import render_fedwatch

st.title("Quốc tế")
view = sidebar.current_view()
tab_charts, tab_fw = st.tabs(["Theo nhóm", "FedWatch"])
with tab_charts:
    chart_page.group_section(view.get("international", {}).get("charts", []), key="intl")
with tab_fw:
    render_fedwatch()
ui.footer()
