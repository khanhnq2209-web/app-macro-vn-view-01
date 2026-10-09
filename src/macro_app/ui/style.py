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

.ma {{ font-size: .8rem; color: {t.STATUS_COLORS["yellow"][1]}; margin: 2px 0; line-height: 1.45; }}
.ma span[title] {{ border-bottom: 1px dotted currentColor; cursor: help; }}

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
.mv-name {{ overflow: hidden; }}
.mv-name a {{ color: {t.TEXT}; text-decoration: none; font-size: .86rem; font-weight: 500;
  display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.mv-name a:hover {{ color: {t.HEADING}; text-decoration: underline; }}
.mv-meta {{ font-size: .68rem; color: {t.MUTED}; margin-top: 1px; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }}
.mv-meta span {{ cursor: help; margin-left: 2px; }}
.mv-spark img {{ display: block; }}
.mv-val {{ text-align: right; white-space: nowrap; }}
.mv-num {{ font-family: {t.FONT}; font-variant-numeric: tabular-nums; font-weight: 600; font-size: 1.02rem; color: {t.TEXT}; }}
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

/* Scorecard v3 */
.sc3-chip {{ display: inline-block; border-radius: 999px; padding: 2px 10px; font-size: .78rem;
  font-weight: 600; white-space: nowrap; }}
.sc3-chip.dash {{ background: transparent !important; border: 1px dashed {t.MUTED}; color: {t.MUTED} !important; }}
.sc3-chip[title] {{ cursor: help; }}
.sc3-cardhead {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
.sc3-cardhead b {{ font-size: 1rem; color: {t.HEADING}; }}
.sc3-badge {{ font-size: .7rem; font-weight: 700; border-radius: 6px; padding: 2px 8px;
  background: {t.STATUS_COLORS["yellow"][0]}; color: {t.STATUS_COLORS["yellow"][1]}; cursor: help; }}
.sc3-score {{ text-align: center; margin-top: -6px; }}
.sc3-num {{ font-family: {t.FONT}; font-variant-numeric: tabular-nums; font-weight: 800; font-size: 2.2rem;
  color: {t.TEXT}; margin-right: 10px; vertical-align: middle; }}
.sc3-sub {{ font-size: .78rem; color: {t.MUTED}; text-align: center; margin-top: 4px; }}
.sc3-title {{ font-size: 1rem; font-weight: 700; color: {t.HEADING}; }}
.sc3-title + .sc3-sub {{ text-align: left; margin-top: 0; }}
.sc3-small {{ font-size: .8rem; color: {t.TEXT}; margin-top: 8px; }}
.sc3-meaning {{ font-size: .8rem; color: {t.TEXT}; background: #F4F6F8; border-radius: 6px;
  padding: 6px 10px; margin-top: 8px; line-height: 1.4; }}
.sc3-sep {{ border: 0; border-top: 1px solid {t.BORDER}; margin: 10px 0 8px 0; }}
.sc3-imp {{ position: relative; border-radius: 10px; padding: 14px 16px; margin: 0; min-height: 100%;
  background: linear-gradient(#fff, #fff) padding-box,
    linear-gradient(120deg, #6d5dfc, #22b8cf, #6d5dfc) border-box;
  border: 1.5px solid transparent; background-size: 100% 100%, 300% 300%;
  animation: sc3-glow 6s ease-in-out infinite; }}
@keyframes sc3-glow {{ 0%, 100% {{ background-position: 0 0, 0% 50%; }} 50% {{ background-position: 0 0, 100% 50%; }} }}
.sc3-imp-head {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; }}
.sc3-ai {{ font-size: 1rem; font-weight: 700; background: linear-gradient(90deg, #6d5dfc, #22b8cf);
  -webkit-background-clip: text; background-clip: text; color: transparent; }}
.sc3-imp-sub {{ font-size: .78rem; color: {t.MUTED}; }}
.sc3-imp ul {{ list-style: none; margin: 6px 0 0 0; padding: 0; }}
.sc3-imp li {{ font-size: .86rem; color: {t.TEXT}; line-height: 1.45; padding: 3px 0;
  opacity: 0; animation: sc3-in .45s ease-out forwards; }}
.sc3-imp li:nth-child(2) {{ animation-delay: .08s; }} .sc3-imp li:nth-child(3) {{ animation-delay: .16s; }}
.sc3-imp li:nth-child(4) {{ animation-delay: .24s; }} .sc3-imp li:nth-child(5) {{ animation-delay: .32s; }}
.sc3-imp li:nth-child(6) {{ animation-delay: .40s; }}
@keyframes sc3-in {{ from {{ opacity: 0; transform: translateY(4px); }} to {{ opacity: 1; transform: none; }} }}
@media (prefers-reduced-motion: reduce) {{ .sc3-imp, .sc3-imp li {{ animation: none; opacity: 1; }} }}
.sc3-imp-mark {{ display: inline-block; width: 18px; font-size: .8rem; }}
.sc3-imp-lbl {{ color: {t.MUTED}; font-weight: 400; }}
.sc-fed-sum {{ font-size: .88rem; color: {t.TEXT}; font-weight: 600; margin: 4px 0 8px 0; }}
.sc3-drv {{ display: grid; grid-template-columns: minmax(110px, 160px) 1fr 50px; gap: 5px 8px;
  align-items: center; font-size: .8rem; margin-top: 8px; }}
.sc3-drv b {{ text-align: right; font-variant-numeric: tabular-nums; }}
.sc3-track {{ height: 10px; position: relative; }}
.sc3-track::before {{ content: ""; position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px;
  background: {t.BORDER}; }}
.sc3-track i {{ position: absolute; top: 0; height: 10px; border-radius: 3px; }}
.sc3-cov {{ height: 8px; border-radius: 4px; background: {t.STATUS_COLORS["none"][0]}; overflow: hidden;
  margin: 6px 0; }}
.sc3-cov i {{ display: block; height: 100%; background: {t.HEADING}; }}
.sc3-chips {{ display: flex; flex-wrap: wrap; gap: 4px; }}
.sc3-alert {{ border-left: 3px solid {t.STATUS_COLORS["yellow"][1]}; background: {t.STATUS_COLORS["yellow"][0]};
  border-radius: 6px; padding: 7px 10px; margin-top: 8px; font-size: .78rem; color: {t.TEXT}; }}
table.sc3 td {{ padding: 6px 6px; }}
table.sc3 tr.sc3-group td {{ background: #F4F6F8; font-size: .84rem; padding: 8px 6px;
  border-bottom: 1px solid {t.BORDER}; }}
table.sc3 tr.sc3-total td {{ border-top: 2px solid {t.HEADING}; border-bottom: 0; font-weight: 700;
  font-size: .86rem; padding-top: 9px; }}
table.sc3 tr.sc3-ex td {{ color: {t.MUTED}; }}
table.sc3 tr.sc3-ex .mv-name a {{ color: {t.MUTED}; }}
.sc3-gnote {{ margin-left: 8px; font-size: .72rem; font-weight: 400; color: {t.MUTED}; }}
.sc3-val {{ font-family: {t.FONT}; font-variant-numeric: tabular-nums; font-weight: 700; font-size: 1rem;
  color: {t.TEXT}; }}
.sc3-cmp {{ font-size: .8rem; white-space: nowrap; cursor: help; }}
.sc3-kind {{ font-size: .74rem; color: {t.MUTED}; }}
table.sc3 td[title] {{ cursor: help; }}
/* Trang cấu hình: thanh lưu dính đáy (Streamlit không có sẵn; Q6 đã duyệt dùng CSS) */
.st-key-cfg_bar {{ position: sticky; bottom: 0; z-index: 50; background: #FFFFFF;
  border-top: 1px solid {t.BORDER}; box-shadow: 0 -4px 14px rgba(0,0,0,.08); padding: 8px 4px 6px 4px; }}
.cfg-sum {{ font-size: .86rem; color: {t.TEXT}; }}
.cfg-sum .cfg-chg {{ font-size: .78rem; color: {t.MUTED}; }}
.cfg-step-ok {{ color: {t.STATUS_COLORS["green"][1]}; font-weight: 700; }}
.cfg-step-bad {{ color: {t.STATUS_COLORS["red"][1]}; font-weight: 700; }}
.cfg-meter {{ display: flex; gap: 2px; height: 10px; border-radius: 5px; overflow: hidden; margin: 6px 0 2px 0; }}
.cfg-meter i {{ display: block; height: 100%; }}
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
