"""Palette + layout dùng chung cho mọi chart; không khai báo lại màu/font ở file khác.

Màu series là 3 slot đầu palette của skill `dataviz` (all-pairs CVD pass cho tối đa 3 series).
"""

from __future__ import annotations

import plotly.graph_objects as go

TEXT = "#13222B"
HEADING = "#1B2A6B"
HIGHLIGHT = "#C0692C"
MUTED = "#5F6B73"
BORDER = "#D5DCE0"

# Màu trạng thái ngưỡng (nền, chữ): chỉ dùng cho trạng thái, không dùng làm series
STATUS_COLORS = {
    "green_strong": ("#D3EBDC", "#1B5E20"),
    "green": ("#E3F1E8", "#2E7D32"),
    "orange": ("#FDE8D7", "#C25E00"),
    "yellow": ("#FBEFD3", "#9A6700"),
    "red": ("#FBE3E1", "#B3261E"),
    "none": ("#ECEEF0", "#5F6B73"),
    "insufficient": ("#ECEEF0", "#5F6B73"),
    "no_data": ("#ECEEF0", "#5F6B73"),
}

# Gán theo thứ tự cố định trong 1 chart; tối đa 3 series để giữ all-pairs CVD pass
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7", "#e34948"]
TARGET_LINE = "#1B2A6B"
GRID = "#E1E0D9"
AXIS = "#C3C2B7"
# Cùng font với Streamlit để chữ, bảng và biểu đồ đồng nhất
FONT = "'Source Sans', 'Source Sans Pro', 'Source Sans 3', system-ui, sans-serif"
CHART_HEIGHT = 340


def apply_theme(
    fig: go.Figure, title: str, y_title: str, *, height: int = CHART_HEIGHT
) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        colorway=CATEGORICAL,
        title={"text": title, "x": 0, "xanchor": "left", "font": {"size": 15, "color": HEADING}},
        yaxis_title=y_title,
        height=height,
        legend={"title": None, "orientation": "h", "yanchor": "top", "y": -0.08, "x": 0},
        margin={"t": 44, "l": 8, "r": 8, "b": 8},
        hovermode="x unified",
        font={"family": FONT, "size": 12, "color": TEXT},
        separators=",.",  # VN: dấu phẩy thập phân, dấu chấm ngàn
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, title=None)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=True, zerolinecolor=AXIS)
    return fig
