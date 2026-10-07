"""CSS của app và chế độ trình bày. Màu lấy từ charts/theme.py."""

from __future__ import annotations

import streamlit as st

from macro_app.charts import theme as t

RULE = "#E3E8EB"

BASE_CSS = f"""
<style>
.block-container {{ max-width: 1440px; padding-top: 3rem; padding-bottom: 2rem; }}
h1, h2, h3 {{ color: {t.HEADING}; }}
h1 {{ font-size: 1.45rem !important; }}

.ms {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 34px; padding: 4px 0 10px 0;
  border-bottom: 1px solid {RULE}; margin-bottom: 6px; }}
.ms-item {{ display: flex; align-items: baseline; gap: 8px; }}
.ms-dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block;
  transform: translateY(-3px); }}
.ms-num {{ font-family: {t.FONT}; font-variant-numeric: tabular-nums; font-weight: 600; font-size: 1.8rem; color: {t.TEXT}; line-height: 1; }}
.ms-lbl {{ font-size: .82rem; color: {t.MUTED}; }}
.ms-note {{ margin-left: auto; font-size: .78rem; color: {t.MUTED}; }}

.ma {{ font-size: .8rem; color: {t.STATUS_COLORS["yellow"][1]}; margin: 2px 0; line-height: 1.45; }}
.ma span[title] {{ border-bottom: 1px dotted currentColor; cursor: help; }}
.mr {{ font-size: .8rem; color: {t.MUTED}; margin: 2px 0 10px 0; }}
.mr b {{ color: {t.TEXT}; font-weight: 600; }}

.mv-title {{ font-size: .72rem; letter-spacing: .08em; text-transform: uppercase; font-weight: 700;
  color: {t.HEADING}; padding: 10px 0 6px 0; border-bottom: 2px solid {t.HEADING}; }}
table.mv {{ width: 100%; border-collapse: collapse; table-layout: fixed; color: {t.TEXT}; }}
table.mv th {{ font-size: .64rem; font-weight: 500; color: {t.MUTED}; text-transform: uppercase;
  letter-spacing: .04em; text-align: left; padding: 6px 6px 4px 6px; border: 0; }}
table.mv th.r {{ text-align: right; }}
table.mv th.c {{ text-align: center; }}
table.mv td {{ padding: 7px 6px; border: 0; border-bottom: 1px solid {RULE}; vertical-align: middle; }}
table.mv tr.mv-group td {{ font-size: .68rem; letter-spacing: .06em; text-transform: uppercase;
  color: {t.MUTED}; font-weight: 600; padding: 12px 6px 4px 6px;
  border-bottom: 1px solid {t.BORDER}; }}
.mv-dot {{ width: 14px; }}
.mv-dot span {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; cursor: help; }}
.mv-name {{ overflow: hidden; }}
.mv-name a {{ color: {t.TEXT}; text-decoration: none; font-size: .86rem; font-weight: 500;
  display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.mv-name a:hover {{ color: {t.HEADING}; text-decoration: underline; }}
.mv-meta {{ font-size: .68rem; color: {t.MUTED}; margin-top: 1px; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }}
.mv-meta span {{ cursor: help; margin-left: 2px; }}
.mv-spark img {{ display: block; }}
.mv-val {{ text-align: right; white-space: nowrap; }}
.mv-num {{ font-family: {t.FONT}; font-variant-numeric: tabular-nums; font-weight: 600; font-size: 1.02rem; color: {t.HIGHLIGHT}; }}
.mv-unit {{ font-family: {t.FONT}; font-size: .7rem; color: {t.MUTED}; margin-left: 3px; }}
.mv-empty {{ font-size: .75rem; color: {t.MUTED}; }}
.mv-chg {{ text-align: right; font-size: .78rem; white-space: nowrap; }}
.mv-basis {{ display: block; font-size: .64rem; color: {t.MUTED}; }}

table.mi tr.mi-group td {{ background: #F4F6F8; padding: 9px 6px; border-bottom: 1px solid {t.BORDER};
  font-size: .82rem; color: {t.TEXT}; }}
table.mi tr.mi-total td {{ background: #FFFFFF; padding: 10px 6px; border-top: 2px solid {t.HEADING};
  border-bottom: 2px solid {t.HEADING}; font-size: .86rem; }}
.mi-gnote {{ margin-left: 10px; font-size: .74rem; color: {t.MUTED}; }}
.mi-cell {{ text-align: center; }}
.mi-cell span {{ display: inline-block; min-width: 30px; padding: 2px 0; border-radius: 6px;
  font-weight: 700; font-size: .95rem; }}
.mi-none {{ color: {t.MUTED}; font-weight: 400 !important; }}

.sc-head {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 24px;
  border-bottom: 2px solid {t.HEADING}; padding-bottom: 10px; margin-bottom: 8px; }}
.sc-name {{ font-size: 1.05rem; font-weight: 700; color: {t.HEADING}; }}
.sc-desc {{ font-size: .78rem; color: {t.MUTED}; max-width: 720px; }}
.sc-score {{ text-align: right; }}
.sc-num {{ font-family: {t.FONT}; font-variant-numeric: tabular-nums; font-weight: 700; font-size: 2.1rem; color: {t.HIGHLIGHT}; margin-right: 10px; }}
.sc-chip {{ display: inline-block; border-radius: 999px; padding: 2px 10px; font-size: .78rem; font-weight: 600; }}
.sc-delta {{ display: block; font-size: .75rem; color: {t.MUTED}; margin-top: 2px; }}
.sc-cov {{ font-size: .68rem; color: {t.MUTED}; }}
.sc-trend {{ font-size: .8rem; font-weight: 600; white-space: nowrap; }}
.sc-arrow {{ font-size: 1.15rem; margin-right: 4px; vertical-align: -2px; }}
.sc-flag {{ color: #9A6700; }}
table.sc-fed {{ max-width: 640px; }}
.sc-warn {{ font-size: .78rem; color: #B3261E; margin: 4px 0 6px 0; }}
.sc-wrap {{ overflow-x: auto; }}
.re-strip {{ display: flex; gap: 2px; margin: 4px 0 2px 0; }}
.re-zone {{ flex: 1 1 0; border-radius: 4px; padding: 6px 8px 8px 8px; font-size: .78rem; line-height: 1.25;
  border: 2px solid transparent; min-width: 0; }}
.re-zone b {{ display: block; font-weight: 600; }}
.re-zone span {{ display: block; font-size: .72rem; opacity: .9; }}
.re-here {{ border-color: {t.HEADING}; }}
.re-now {{ font-size: .7rem; font-weight: 700; margin-top: 3px; color: {t.HEADING}; }}
.cfg-bar {{ display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; font-size: .85rem; color: {t.MUTED}; }}
.cfg-bar b {{ color: {t.HEADING}; font-size: 1.05rem; }}
.sc-wrap table.mv {{ min-width: 680px; }}
@media (max-width: 640px) {{
  .sc-head {{ flex-direction: column; align-items: flex-start; gap: 6px; }}
  .sc-score {{ text-align: left; }}
  table.mv {{ table-layout: auto; }}
  table.mv col {{ width: auto !important; }}
  .sc-wrap table.mv {{ min-width: 0; }}
  .m-hide {{ display: none !important; }}
  .mv-name {{ overflow: visible; }}
  .mv-name a {{ white-space: normal; overflow: visible; line-height: 1.25; }}
  .mv-meta {{ white-space: normal; }}
  .mv-num {{ font-size: .95rem; }}
  table.mv td {{ padding: 6px 4px; }}
  [data-testid="stMetricValue"] {{ font-size: 1.35rem; }}
  [data-testid="stMetric"] {{ padding: 0; }}
}}
table.mv td.r, table.mv th.r {{ text-align: right; }}

.mc-note {{ font-size: 0.78rem; color: {t.MUTED}; }}
.mc-footer {{ font-size: 0.72rem; color: {t.MUTED}; border-top: 1px solid {RULE};
  margin-top: 1.5rem; padding-top: .5rem; }}
</style>
"""

PRESENT_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
header[data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer,
[data-testid="stDecoration"], [data-testid="stStatusWidget"], .stButton { display: none !important; }
.block-container { max-width: 1840px !important; padding: 1.4rem 2.4rem !important; }
.mv-name a { font-size: .95rem; }
.mv-num { font-size: 1.3rem; }
.ms-num { font-size: 2.3rem; }
table.mv td { padding: 5px 6px; }
table.mv tr.mv-group td { padding-top: 9px; }
.mv-title { padding-top: 4px; }
.st-key-present_exit .stButton { display: block !important; }
</style>
"""


def inject(present: bool) -> None:
    st.html(BASE_CSS)
    if present:
        st.html(PRESENT_CSS)
