"""Gộp file Excel người dùng xuất từ dulieukinhte.com (`data/inbox/`) vào file raw (D7).

Ghép sheet:
- Sheet wide (cột nhãn + cột kỳ) → sheet raw **cùng tên** (tên sheet xuất = "{bảng} ({đơn vị})",
  cắt 31 ký tự). Gộp theo (dòng chỉ tiêu × kỳ): hợp các kỳ, ô trùng → bản mới thắng
  (nguồn sửa lùi số), sắp cột kỳ theo thời gian. Vượt 16.384 cột Excel → báo lỗi, không ghi.
- Sheet long (cột đầu là ngày) → sheet raw có **cùng tập tiêu đề**; upsert theo ngày.

Sao lưu file raw vào `_backup/<timestamp>/` trước khi ghi; ghi bằng openpyxl giữ các sheet khác.
Sheet không khớp → báo, file ở lại inbox. File gộp hết → chuyển vào `inbox/_merged/<timestamp>/`.
Log mỗi sheet: `data/raw/_merge_log.csv`.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

from macro_app.io.wide_sheet import frame_to_number, header_text, period_to_date, split_columns
from macro_app.paths import BACKUP_DIR, INBOX_DIR, RAW_DIR

MAX_EXCEL_COLUMNS = 16_384
LOG_NAME = "_merge_log.csv"
MERGED_SUBDIR = "_merged"
LOG_COLUMNS = [
    "timestamp",
    "inbox_file",
    "raw_file",
    "sheet",
    "periods_added",
    "cells_changed",
    "cells_filled",
    "rows_added",
    "status",
]
_KEY_SEP = "\x1f"
_SAMPLE_ROWS = 6


@dataclass(frozen=True)
class SheetInfo:
    path: Path
    sheet: str
    kind: str | None  # "wide" | "long" | None
    header: tuple[str, ...]


@dataclass
class MergeContext:
    raw_index: list[SheetInfo]
    backup_dir: Path
    stamp: str
    backed_up: set[Path] = field(default_factory=set)


# ---------------------------------------------------------------- nhận dạng sheet


def _trim_header(row: tuple) -> list[str]:
    texts = [header_text(v) for v in row]
    while texts and texts[-1] == "":
        texts.pop()
    return texts


def _looks_like_dates(values: list) -> bool:
    """Cột ngày: ô datetime hoặc chuỗi ngày (số nguyên như STT không tính)."""
    present = [v for v in values if v not in (None, "")]
    if not present:
        return False
    texts = pd.Series([v for v in present if isinstance(v, str)], dtype=object)
    parsed = pd.to_datetime(texts, errors="coerce", dayfirst=True)
    n_dates = sum(isinstance(v, datetime) for v in present) + int(parsed.notna().sum())
    return n_dates >= 0.8 * len(present)


def classify_sheet(header: list[str], first_col: list) -> str | None:
    """'wide' (cột nhãn + cột kỳ), 'long' (cột đầu là ngày) hoặc None."""
    if not header:
        return None
    labels, periods = split_columns(pd.Index(header))
    if labels and periods:
        return "wide"
    if _looks_like_dates(first_col):
        return "long"
    return None


def scan_workbook(path: Path) -> list[SheetInfo]:
    """Tiêu đề + loại của mọi sheet (đọc vài dòng đầu, read-only)."""
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        infos = []
        for ws in book.worksheets:
            rows = list(ws.iter_rows(max_row=_SAMPLE_ROWS, values_only=True))
            header = _trim_header(rows[0]) if rows else []
            first_col = [r[0] for r in rows[1:] if r]
            infos.append(
                SheetInfo(path, ws.title, classify_sheet(header, first_col), tuple(header))
            )
        return infos
    finally:
        book.close()


def build_raw_index(raw_dir: Path) -> list[SheetInfo]:
    files = sorted(p for p in raw_dir.glob("*.xlsx") if not p.name.startswith("~$"))
    return [info for path in files for info in scan_workbook(path)]


def find_target(info: SheetInfo, raw_index: list[SheetInfo]) -> list[SheetInfo]:
    """Sheet raw khớp: wide → cùng tên sheet; long → cùng tập tiêu đề."""
    if info.kind == "wide":
        return [r for r in raw_index if r.kind == "wide" and r.sheet == info.sheet]
    if info.kind == "long":
        wanted = set(info.header)
        return [r for r in raw_index if r.kind == "long" and set(r.header) == wanted]
    return []


# ---------------------------------------------------------------- gộp ô


def _differs(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Ô có giá trị ở cả hai bên và khác nhau (số so gần đúng, chữ so chuỗi)."""
    o_num, n_num = frame_to_number(old), frame_to_number(new)
    both_num = o_num.notna() & n_num.notna()
    num_diff = ~np.isclose(o_num.fillna(0), n_num.fillna(0), rtol=1e-9, atol=1e-12)
    text_diff = old.astype(str).to_numpy() != new.astype(str).to_numpy()
    diff = np.where(both_num.to_numpy(), num_diff, text_diff)
    present = old.notna().to_numpy() & new.notna().to_numpy()
    return pd.DataFrame(present & diff, index=old.index, columns=old.columns)


def combine_cells(old: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Hợp 2 bảng (index = khóa dòng, cột = kỳ/chỉ tiêu); ô mới khác NaN thắng.

    Thứ tự: dòng/cột cũ trước, dòng/cột mới thêm sau (người gọi tự sắp lại cột nếu cần).
    """
    rows = old.index.append(new.index.difference(old.index, sort=False))
    cols = old.columns.append(new.columns.difference(old.columns, sort=False))
    o = old.reindex(index=rows, columns=cols)
    n = new.reindex(index=rows, columns=cols)
    merged = n.where(n.notna(), o)
    in_old = pd.DataFrame(
        np.outer(rows.isin(old.index), cols.isin(old.columns)), index=rows, columns=cols
    )
    stats = {
        "cells_changed": int(_differs(o, n).to_numpy().sum()),
        "cells_filled": int((in_old & o.isna() & n.notna()).to_numpy().sum()),
        "rows_added": len(rows) - len(old.index),
        "cols_added": len(cols) - len(old.columns),
    }
    return merged, stats


# ---------------------------------------------------------------- sheet wide


@dataclass
class WideFrame:
    labels: pd.DataFrame  # cột nhãn, giữ nguyên chữ (cả thụt lề); index = khóa dòng
    values: pd.DataFrame  # index = khóa dòng, cột = ngày cuối kỳ
    headers: dict[pd.Timestamp, str]  # ngày → chữ tiêu đề kỳ


def _row_keys(labels: pd.DataFrame) -> pd.Index:
    parts = [labels[c].astype("string").fillna("").str.strip() for c in labels.columns]
    key = parts[0].str.cat(parts[1:], sep=_KEY_SEP) if len(parts) > 1 else parts[0]
    occurrence = key.groupby(key).cumcount().astype(str)
    return pd.Index(key + _KEY_SEP + occurrence, name="row_key")


def split_wide(frame: pd.DataFrame) -> WideFrame:
    label_cols, period_cols = split_columns(frame.columns)
    dates = period_to_date(pd.Index(period_cols))
    if dates.has_duplicates:
        raise ValueError("Sheet có cột kỳ trùng nhau")
    keys = _row_keys(frame[label_cols])
    labels = frame[label_cols].set_axis(keys)
    raw_values = frame[period_cols].set_axis(keys).set_axis(dates, axis=1)
    values = frame_to_number(raw_values)
    headers = dict(zip(dates, (header_text(c) for c in period_cols), strict=True))
    return WideFrame(labels, values, headers)


def merge_wide_frames(old: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Gộp 2 sheet wide → (sheet gộp để ghi, thống kê)."""
    o, n = split_wide(old), split_wide(new)
    if [header_text(c) for c in o.labels.columns] != [header_text(c) for c in n.labels.columns]:
        raise ValueError("Cột nhãn khác nhau giữa file mới và file raw")
    values, stats = combine_cells(o.values, n.values)
    values = values.reindex(columns=values.columns.sort_values())
    n_cols = len(o.labels.columns) + len(values.columns)
    if n_cols > MAX_EXCEL_COLUMNS:
        raise ValueError(f"Kết quả {n_cols} cột vượt giới hạn Excel {MAX_EXCEL_COLUMNS}")
    labels = pd.concat([o.labels, n.labels.loc[n.labels.index.difference(o.labels.index)]])
    headers = n.headers | o.headers  # giữ chữ tiêu đề cũ cho kỳ đã có
    out_values = values.set_axis([headers[d] for d in values.columns], axis=1)
    out = pd.concat([labels.loc[values.index], out_values], axis=1).reset_index(drop=True)
    stats["periods_added"] = stats.pop("cols_added")
    return out, stats


# ---------------------------------------------------------------- sheet long


def _long_indexed(frame: pd.DataFrame) -> pd.DataFrame:
    date_col = frame.columns[0]
    dates = pd.to_datetime(frame[date_col], errors="coerce", dayfirst=True).dt.normalize()
    out = frame.drop(columns=date_col).set_axis(pd.DatetimeIndex(dates, name="date"))
    out = out[out.index.notna()]
    return out[~out.index.duplicated(keep="last")]


def merge_long_frames(old: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Upsert sheet long theo ngày; tiêu đề khớp sau khi strip, giữ chữ tiêu đề cũ."""
    rename = {c: o for c in new.columns for o in old.columns if str(c).strip() == str(o).strip()}
    new = new.rename(columns=rename)[list(old.columns)]
    merged, stats = combine_cells(_long_indexed(old), _long_indexed(new))
    out = merged.sort_index().reset_index().rename(columns={"date": old.columns[0]})
    stats.pop("cols_added")
    stats["periods_added"] = stats["rows_added"]  # long: mỗi dòng mới = 1 kỳ mới
    return out[list(old.columns)], stats


# ---------------------------------------------------------------- ghi file


def read_sheet(path: Path, sheet: str) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet, header=0, dtype=object, engine="openpyxl")


def _backup_once(path: Path, ctx: MergeContext) -> None:
    if path in ctx.backed_up:
        return
    target = ctx.backup_dir / ctx.stamp / path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    ctx.backed_up.add(path)


def write_sheet(path: Path, sheet: str, frame: pd.DataFrame) -> None:
    """Thay 1 sheet, giữ nguyên các sheet khác và vị trí sheet."""
    with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        frame.to_excel(writer, sheet_name=sheet, index=False)


def merge_sheet(info: SheetInfo, ctx: MergeContext) -> dict:
    """Gộp 1 sheet inbox vào sheet raw tương ứng → dòng báo cáo."""
    result = {"sheet": info.sheet, "kind": info.kind, "raw_file": None}
    targets = find_target(info, ctx.raw_index)
    if len(targets) != 1:
        reason = "không khớp sheet raw nào" if not targets else f"khớp {len(targets)} sheet raw"
        return result | {"status": "unmatched", "message": reason}
    target = targets[0]
    result["raw_file"] = target.path.name
    merge = merge_wide_frames if info.kind == "wide" else merge_long_frames
    try:
        out, stats = merge(read_sheet(target.path, target.sheet), read_sheet(info.path, info.sheet))
    except ValueError as exc:
        return result | {"status": "error", "message": str(exc)}
    result |= stats
    if not any(stats[k] for k in ("periods_added", "cells_changed", "cells_filled", "rows_added")):
        return result | {"status": "unchanged"}
    _backup_once(target.path, ctx)
    write_sheet(target.path, target.sheet, out)
    return result | {"status": "merged"}


def append_log(log_path: Path, inbox_file: str, sheets: list[dict], stamp: str) -> None:
    rows = pd.DataFrame(sheets).assign(timestamp=stamp, inbox_file=inbox_file)
    rows = rows.reindex(columns=LOG_COLUMNS)
    counts = ["periods_added", "cells_changed", "cells_filled", "rows_added"]
    rows[counts] = rows[counts].astype("Int64")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(log_path, mode="a", header=not log_path.exists(), index=False, encoding="utf-8-sig")


def merge_inbox_file(path: Path, ctx: MergeContext, inbox_dir: Path) -> dict:
    sheets = [merge_sheet(info, ctx) for info in scan_workbook(path)]
    ok = all(s["status"] in ("merged", "unchanged") for s in sheets)
    report = {"inbox_file": path.name, "sheets": sheets, "moved_to": None}
    if ok and sheets:
        dest = inbox_dir / MERGED_SUBDIR / ctx.stamp / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), dest)
        report["moved_to"] = str(dest)
    report["status"] = "merged" if report["moved_to"] else "partial"
    return report


def merge_inbox(
    inbox_dir: Path = INBOX_DIR, raw_dir: Path = RAW_DIR, backup_dir: Path = BACKUP_DIR
) -> list[dict]:
    """Gộp mọi file `.xlsx` trong inbox vào raw. Trả báo cáo theo file (kèm từng sheet)."""
    files = sorted(p for p in inbox_dir.glob("*.xlsx") if not p.name.startswith("~$"))
    if not files:
        return []
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    ctx = MergeContext(build_raw_index(raw_dir), backup_dir, stamp)
    reports = []
    for path in files:
        report = merge_inbox_file(path, ctx, inbox_dir)
        append_log(raw_dir / LOG_NAME, path.name, report["sheets"], stamp)
        reports.append(report)
    return reports
