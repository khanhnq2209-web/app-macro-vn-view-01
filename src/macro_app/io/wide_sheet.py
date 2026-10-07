"""Đọc sheet "wide" xuất từ dulieukinhte.com (dòng = chỉ tiêu, cột = kỳ).

Nhãn thụt đầu dòng 4 dấu cách/cấp. Cột kỳ `dd-mm-yyyy`, `mm-yyyy`, `Qn-yyyy`, `yyyy`;
tháng, quý, năm quy về ngày cuối kỳ.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

GROUPED_LABEL = "Chỉ tiêu (gộp cấp)"
INDENT_WIDTH = 4
LABEL_SEPARATOR = " - "

_DAY_RE = r"\d{1,2}-\d{1,2}-\d{4}"
_MONTH_RE = r"\d{1,2}-\d{4}"
_QUARTER_RE = r"Q([1-4])-(\d{4})"
_YEAR_RE = r"\d{4}"


def header_text(value: object) -> str:
    """Tiêu đề cột thành chuỗi (Excel có thể trả năm dạng số, ngày dạng datetime)."""
    if isinstance(value, dt.datetime | dt.date | pd.Timestamp):
        return pd.Timestamp(value).strftime("%d-%m-%Y")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "" if value is None else str(value).strip()


def period_to_date(labels: object) -> pd.DatetimeIndex:
    """Nhãn kỳ thành ngày cuối kỳ; nhãn không phải kỳ thành NaT."""
    text = pd.Series([header_text(v) for v in labels], dtype="string")
    day = pd.to_datetime(
        text.where(text.str.fullmatch(_DAY_RE)), format="%d-%m-%Y", errors="coerce"
    )
    month = pd.to_datetime(
        text.where(text.str.fullmatch(_MONTH_RE)), format="%m-%Y", errors="coerce"
    ) + pd.offsets.MonthEnd(0)
    year = pd.to_datetime(text.where(text.str.fullmatch(_YEAR_RE)), format="%Y", errors="coerce")
    year = year + pd.offsets.YearEnd(0)
    quarter = _quarter_end(text)
    out = day.fillna(month).fillna(quarter).fillna(year)
    return pd.DatetimeIndex(out.to_numpy(), name="date")


def _quarter_end(text: pd.Series) -> pd.Series:
    is_quarter = text.str.fullmatch(_QUARTER_RE)
    last_month = text.str.replace(
        rf"^{_QUARTER_RE}$", lambda m: f"{int(m[1]) * 3}-{m[2]}", regex=True
    )
    stamp = pd.to_datetime(last_month.where(is_quarter), format="%m-%Y", errors="coerce")
    return stamp + pd.offsets.MonthEnd(0)


def to_number(values: pd.Series, thousands_sep: str | None = None) -> pd.Series:
    """Ép số: `"5,5"` là 5.5, `"1.234,5"` là 1234.5, `"N/A"` và `"-"` là NaN.

    Không cho `thousands_sep`: có cả `,` và `.` thì ký tự đứng sau cùng là dấu thập phân;
    chỉ có `,` thì `,` là dấu thập phân (kiểu Việt Nam).
    """
    if pd.api.types.is_numeric_dtype(values):
        return values.astype(float)
    text = values.astype("string").str.strip().str.replace(" ", "", regex=False)
    if thousands_sep is not None:
        text = text.str.replace(thousands_sep, "", regex=False)
        return pd.to_numeric(text, errors="coerce").astype(float)
    last_comma, last_dot = text.str.rfind(","), text.str.rfind(".")
    comma_decimal = last_comma > last_dot
    dot_decimal = (last_dot > last_comma) & (last_comma >= 0)
    text = text.mask(dot_decimal, text.str.replace(",", "", regex=False))
    comma_text = text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    text = text.mask(comma_decimal, comma_text)
    return pd.to_numeric(text, errors="coerce").astype(float)


def frame_to_number(frame: pd.DataFrame) -> pd.DataFrame:
    """`to_number` cho cả bảng (ép 1 lần trên mảng phẳng, không lặp từng cột)."""
    flat = to_number(pd.Series(frame.to_numpy(dtype=object).ravel(), dtype=object))
    return pd.DataFrame(
        flat.to_numpy().reshape(frame.shape), index=frame.index, columns=frame.columns
    )


def split_columns(columns: pd.Index) -> tuple[list, list]:
    """(cột nhãn đứng đầu, cột kỳ). Cột nhãn = các cột trước cột kỳ đầu tiên."""
    dates = period_to_date(columns)
    is_period = ~dates.isna()
    if not is_period.any():
        return list(columns), []
    first = int(np.argmax(is_period))
    periods = [c for c, ok in zip(columns[first:], is_period[first:], strict=True) if ok]
    return list(columns[:first]), periods


def _clean_text(values: pd.Series) -> pd.Series:
    return values.astype("string").fillna("").str.replace(" ", " ", regex=False)


def row_labels(frame: pd.DataFrame, label_cols: list) -> pd.DataFrame:
    """Nhãn dòng (đã strip), cấp thụt lề và nhãn dòng cha cho từng dòng.

    Có `Chỉ tiêu (gộp cấp)` khác rỗng thì dùng nó; không thì ghép các cột nhãn bằng " - ".
    """
    texts = {header_text(c): _clean_text(frame[c]) for c in label_cols}
    last = texts[header_text(label_cols[-1])]
    level = ((last.str.len() - last.str.lstrip().str.len()) // INDENT_WIDTH).astype(int)
    grouped = texts.pop(GROUPED_LABEL, None)
    label = _join_nonempty([t.str.strip() for t in texts.values()])
    if grouped is not None:
        grouped = grouped.str.strip()
        label = grouped.where(grouped.ne(""), label)
    return pd.DataFrame({"row_label": label, "level": level, "parent": _parents(label, level)})


def _join_nonempty(parts: list[pd.Series]) -> pd.Series:
    joined = parts[0]
    for part in parts[1:]:
        both = joined.ne("") & part.ne("")
        joined = (joined + LABEL_SEPARATOR + part).where(both, joined.where(joined.ne(""), part))
    return joined


def _parents(label: pd.Series, level: pd.Series) -> pd.Series:
    """Nhãn dòng gần nhất phía trên có cấp nhỏ hơn đúng 1 (dòng cha)."""
    parent = pd.Series("", index=label.index, dtype="string")
    for lv in sorted(level.unique()):
        if lv == 0:
            continue
        candidates = label.where(level == lv - 1).ffill().fillna("")
        parent = parent.mask(level == lv, candidates)
    return parent


def wide_to_long(frame: pd.DataFrame) -> pd.DataFrame:
    """Sheet wide (header ở dòng đầu) sang long [row_label, parent, level, row_pos, date, value]."""
    label_cols, period_cols = split_columns(frame.columns)
    if not label_cols or not period_cols:
        raise ValueError("Sheet không có dạng wide (cột nhãn + cột kỳ)")
    labels = row_labels(frame, label_cols).assign(row_pos=np.arange(len(frame)))
    values = frame_to_number(frame[period_cols])
    values.columns = period_to_date(pd.Index(period_cols))
    values.index = labels.index
    long = values.rename_axis("_row").reset_index()
    long = long.melt(id_vars="_row", var_name="date", value_name="value")
    long["date"] = pd.to_datetime(long["date"])  # melt trả cột object
    long = long.join(labels, on="_row").drop(columns="_row")
    long = long.sort_values(["row_pos", "date"], ignore_index=True)
    return long[["row_label", "parent", "level", "row_pos", "date", "value"]]


def first_wide_sheet(path: Path) -> str:
    """Tên sheet wide đầu tiên của workbook (bỏ qua `Sheet1` dạng long)."""
    names = pd.ExcelFile(path, engine="openpyxl").sheet_names
    wide = [n for n in names if n != "Sheet1"]
    if not wide:
        raise ValueError(f"{path.name}: không có sheet wide")
    return wide[0]


def read_wide_sheet(path: Path, sheet: str | None = None) -> pd.DataFrame:
    """Đọc 1 sheet wide thành long (xem `wide_to_long`)."""
    sheet = sheet or first_wide_sheet(path)
    frame = pd.read_excel(path, sheet_name=sheet, header=0, dtype=object, engine="openpyxl")
    return wide_to_long(frame)
