"""VBMA: file CSV tĩnh công khai vào cache `data/cache/vbma.xlsx` (nguồn tùy chọn).

Đường dẫn CSV lấy từ `vbma.org.vn/js/markets/*.js`. File phần lớn UTF-16LE + tab, một số UTF-8 +
dấu phẩy; số có dấu phẩy ngăn nghìn; ô trống ghi `N/A`, `#N/A`, `-`.
"""

from __future__ import annotations

import io
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from macro_app.io import excel_cache
from macro_app.io.vn_raw import finalize_store
from macro_app.io.wide_sheet import to_number
from macro_app.paths import CACHE_DIR

log = logging.getLogger(__name__)

BASE_URL = "https://vbma.org.vn/csv/markets"
SOURCE = "VBMA"
DEFAULT_CACHE = CACHE_DIR / "vbma.xlsx"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
TIMEOUT_SECONDS = 30
BUDGET_FIRST_YEAR = 2018  # năm đầu của bảng thu chi NSNN theo năm trên VBMA
HEATMAP = "tables/vi/tong_quan_kinh_te_vi_mo.csv"
PMI_CHART = "charts/vi/pmi.csv"
GDP_TABLE = "tables/vi/gdp_thuc_te_theo_quy.csv"
BUDGET_TABLE = "tables/vi/thu_chi_ngan_sach_theo_nam_{year}.csv"
LAND_USE_ROW = "Thu tiền sử dụng đất"
REALESTATE_ROW = "Hoạt động kinh doanh bất động sản"
HEATMAP_ROWS = {
    "vbma.pmi_heatmap": "Chỉ số PMI",
    "vbma.cpi_housing_yoy": "Nhà ở và VLXD",
    "vbma.cpi_yoy": "Lạm phát",
    "vbma.core_inflation_yoy": "Lạm phát cơ bản",
    "vbma.gdp_yoy": "Tăng trưởng GDP thực tế",  # % YoY công bố, lặp lại 3 tháng/quý
}
_THOUSANDS = ","


# ---------------------------------------------------------------- tải + giải mã


def decode_csv(content: bytes) -> pd.DataFrame:
    """Byte CSV thành bảng chuỗi (không header). Tự nhận UTF-16/UTF-8 và tab/phẩy."""
    if content[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = content.decode("utf-16")
    else:
        text = content.decode("utf-8-sig")
    first_line = text.split("\n", 1)[0]
    sep = "\t" if "\t" in first_line else ","
    return pd.read_csv(
        io.StringIO(text), sep=sep, header=None, dtype=str, keep_default_na=False
    ).apply(lambda col: col.str.strip())


def fetch_csv(session: requests.Session, path: str) -> pd.DataFrame | None:
    """Tải 1 file CSV; 404 trả None (vd bảng ngân sách năm chưa có)."""
    resp = session.get(
        f"{BASE_URL}/{path}", headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    if resp.content[:20].lstrip().lower().startswith((b"<!doctype", b"<html")):
        return None
    return decode_csv(resp.content)


# ---------------------------------------------------------------- nhãn kỳ


_PERIOD_PATTERNS = [  # (regex, nhóm tháng, nhóm năm, nhân tháng)
    (r"^T(\d{1,2}) (\d{4})$", 1, 2, 1),  # T8 2026
    (r"^(\d{1,2})T (\d{4})$", 1, 2, 1),  # 12T 2018 (lũy kế đến tháng 12)
    (r"^Q([1-4]) (\d{4})$", 1, 2, 3),  # Q1 2015
    (r"^\d{1,2}/(\d{1,2})/(\d{4})$", 1, 2, 1),  # 1/5/2026 (ngày/tháng/năm, đại diện tháng)
]


def vbma_period_to_date(labels: pd.Series) -> pd.Series:
    """Nhãn kỳ VBMA thành ngày cuối tháng/quý; nhãn khác thành NaT."""
    text = labels.astype("string").str.strip()
    out = pd.Series(pd.NaT, index=labels.index, dtype="datetime64[ns]")
    for pattern, m_group, y_group, factor in _PERIOD_PATTERNS:
        parts = text.str.extract(pattern)
        month = pd.to_numeric(parts[m_group - 1], errors="coerce") * factor
        year = pd.to_numeric(parts[y_group - 1], errors="coerce")
        stamp = pd.to_datetime(
            year.astype("Int64").astype("string") + "-" + month.astype("Int64").astype("string"),
            format="%Y-%m",
            errors="coerce",
        )
        out = out.fillna(stamp + pd.offsets.MonthEnd(0))
    return out


def find_row(table: pd.DataFrame, label: str, *, prefix: bool = False) -> int:
    labels = table[0].str.strip()
    mask = labels.str.startswith(label) if prefix else labels.eq(label)
    hits = table.index[mask]
    if len(hits) == 0:
        raise ValueError(f"VBMA: không thấy dòng '{label}'")
    return int(hits[0])


def row_series(table: pd.DataFrame, row: int, first_col: int, header_row: int = 0) -> pd.Series:
    """1 dòng bảng thành Series số theo ngày (bỏ ô không phải số, kỳ không đọc được)."""
    dates = vbma_period_to_date(table.iloc[header_row, first_col:])
    values = to_number(table.iloc[row, first_col:], thousands_sep=_THOUSANDS)
    series = pd.Series(values.to_numpy(), index=pd.DatetimeIndex(dates.to_numpy(), name="date"))
    series = series[series.index.notna()].dropna()
    return series[~series.index.duplicated(keep="last")].sort_index()


def _frame(series: pd.Series) -> pd.DataFrame:
    return series.rename("value").rename_axis("date").reset_index()


# ---------------------------------------------------------------- bộ đọc từng file


def parse_pmi_chart(table: pd.DataFrame) -> pd.Series:
    return row_series(table, find_row(table, "PMI"), first_col=1)


def parse_heatmap(table: pd.DataFrame) -> dict[str, pd.Series]:
    """Heatmap vĩ mô: cột 0 = chỉ tiêu, cột 1 = đơn vị, từ cột 2 = tháng."""
    return {
        sid: row_series(table, find_row(table, label), 2) for sid, label in HEATMAP_ROWS.items()
    }


def parse_gdp_table(table: pd.DataFrame) -> dict[str, pd.Series]:
    level = row_series(table, find_row(table, REALESTATE_ROW, prefix=True), first_col=1)
    previous = level.reindex(level.index - pd.DateOffset(years=1))  # ngày đã là cuối quý
    yoy = (level / previous.to_numpy() - 1) * 100
    return {"vbma.gdp_real_realestate": level, "vbma.gdp_realestate_yoy": yoy.dropna()}


def budget_actual_columns(table: pd.DataFrame) -> pd.Series:
    """Cột 'Thực hiện' kèm nhãn kỳ 'nT YYYY'.

    Tiêu đề kỳ là ô gộp 2 cột (Thực hiện, % thực hiện), chữ nằm ở cột thứ hai,
    nên ô '-' lấy nhãn của cột bên phải.
    """
    header = table.iloc[0].where(~table.iloc[0].isin(["-", ""]))
    period = header.fillna(header.shift(-1))
    is_period = period.fillna("").str.match(r"^\d{1,2}T \d{4}$")
    is_actual = table.iloc[1].eq("Thực hiện") & is_period
    return period[is_actual]


def parse_budget_table(table: pd.DataFrame) -> dict[str, pd.Series]:
    """Bảng thu chi NSNN 1 năm: thực hiện lũy kế 'nT YYYY' + 'Dự toán YYYY' (tỷ đồng)."""
    row = find_row(table, LAND_USE_ROW)
    actual = budget_actual_columns(table)
    ytd = pd.Series(
        to_number(table.iloc[row][actual.index], thousands_sep=_THOUSANDS).to_numpy(),
        index=pd.DatetimeIndex(vbma_period_to_date(actual).to_numpy(), name="date"),
    ).dropna()
    header = table.iloc[0]
    plan_cols = header.index[header.str.match(r"^Dự toán \d{4}$")]
    plan = pd.Series(dtype=float)
    if len(plan_cols):
        year = int(header[plan_cols[0]].split()[-1])
        value = to_number(table.iloc[row][plan_cols[:1]], thousands_sep=_THOUSANDS)
        plan = pd.Series(value.to_numpy(), index=pd.DatetimeIndex([pd.Timestamp(year, 12, 31)]))
    return {
        "vbma.land_use_revenue": ytd[ytd.index.month == 12],
        "vbma.land_use_revenue_ytd": ytd,
        "vbma.land_use_revenue_plan": plan.dropna(),
    }


# ---------------------------------------------------------------- điều phối


@dataclass(frozen=True)
class Job:
    paths: list[str]
    series_ids: list[str]
    parse: Callable[[list[pd.DataFrame]], dict[str, pd.Series]]


def _concat_parts(parts: list[dict[str, pd.Series]]) -> dict[str, pd.Series]:
    """Nối các dict {series_id: Series} (vd bảng ngân sách từng năm)."""
    pieces: dict[str, list[pd.Series]] = {}
    for part in parts:
        for key, values in part.items():
            pieces.setdefault(key, []).extend([values] if not values.empty else [])
    out = {}
    for key, items in pieces.items():
        joined = pd.concat(items).sort_index() if items else pd.Series(dtype=float)
        out[key] = joined[~joined.index.duplicated(keep="last")]
    return out


def parse_budget_tables(tables: list[pd.DataFrame]) -> dict[str, pd.Series]:
    """Ghép bảng ngân sách các năm; bỏ năm có số liệu y hệt năm trước (VBMA chép nhầm bảng,
    vd bảng 2021 trùng 2020 từng ô)."""
    parts, previous = [], None
    for table in tables:
        part = parse_budget_table(table)
        values = part["vbma.land_use_revenue_ytd"].to_numpy()
        if previous is not None and len(values) and np.array_equal(values, previous):
            log.warning("VBMA: bảng ngân sách trùng năm trước → bỏ %s", values[:1])
            continue
        parts.append(part)
        previous = values
    return _concat_parts(parts)


def build_jobs(last_year: int) -> list[Job]:
    budget_paths = [BUDGET_TABLE.format(year=y) for y in range(BUDGET_FIRST_YEAR, last_year + 1)]
    return [
        Job([PMI_CHART], ["vbma.pmi_chart"], lambda t: {"vbma.pmi_chart": parse_pmi_chart(t[0])}),
        Job([HEATMAP], list(HEATMAP_ROWS), lambda t: parse_heatmap(t[0])),
        Job(
            [GDP_TABLE],
            ["vbma.gdp_real_realestate", "vbma.gdp_realestate_yoy"],
            lambda t: parse_gdp_table(t[0]),
        ),
        Job(
            budget_paths,
            ["vbma.land_use_revenue", "vbma.land_use_revenue_ytd", "vbma.land_use_revenue_plan"],
            parse_budget_tables,
        ),
    ]


def run_job(job: Job, session: requests.Session, sleep: float) -> dict[str, pd.Series]:
    tables = []
    for path in job.paths:
        time.sleep(sleep)
        table = fetch_csv(session, path)
        if table is not None:
            tables.append(table)
    if not tables:
        raise ValueError(f"VBMA: không tải được {job.paths[0]}")
    return job.parse(tables)


def combine_pmi(series: dict[str, pd.Series]) -> dict[str, pd.Series]:
    """`vbma.pmi` = chuỗi chart; tháng chart chưa có lấy từ heatmap (heatmap cập nhật sớm hơn)."""
    chart = series.pop("vbma.pmi_chart", pd.Series(dtype=float))
    heat = series.get("vbma.pmi_heatmap", pd.Series(dtype=float))
    if chart.empty and heat.empty:
        return series
    extra = heat[~heat.index.isin(chart.index)]
    series["vbma.pmi"] = pd.concat([chart, extra]).sort_index()
    return series


def _meta_row(sid: str, series: pd.Series | None, error: str, fetched_at: str) -> dict:
    ok = series is not None and not series.empty
    return {
        "series_id": sid,
        "sheet": excel_cache.sheet_name_for(sid),
        "fetched_at": fetched_at,
        "n_obs": len(series) if ok else 0,
        "last_date": series.index.max().date().isoformat() if ok else None,
        "status": "ok" if ok else "error",
        "error": "" if ok else (error or "rỗng"),
    }


def collect_series(session: requests.Session, sleep: float, last_year: int) -> tuple[dict, dict]:
    """Chạy mọi job; trả ({series_id: Series}, {series_id: lỗi})."""
    series: dict[str, pd.Series] = {}
    errors: dict[str, str] = {}
    for job in build_jobs(last_year):
        try:
            series |= run_job(job, session, sleep)
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            log.warning("VBMA job %s lỗi: %s", job.paths[0], type(exc).__name__)
            errors |= dict.fromkeys(job.series_ids, f"{type(exc).__name__}: {exc}"[:200])
    series = combine_pmi(series)
    if "vbma.pmi_chart" in errors and "vbma.pmi" not in series:
        errors["vbma.pmi"] = errors["vbma.pmi_chart"]
    errors.pop("vbma.pmi_chart", None)
    return series, errors


def fetch_vbma(
    cache_path: Path = DEFAULT_CACHE,
    session: requests.Session | None = None,
    sleep: float = 1.5,
    last_year: int | None = None,
) -> pd.DataFrame:
    """Tải CSV VBMA và ghi cache Excel (series lỗi giữ bản cache cũ). Trả bảng `_meta`."""
    session = session or requests.Session()
    series, errors = collect_series(session, sleep, last_year or date.today().year)
    fetched_at = excel_cache.utc_now_iso()
    ids = sorted(set(series) | set(errors))
    meta = pd.DataFrame([_meta_row(s, series.get(s), errors.get(s, ""), fetched_at) for s in ids])
    new_frames = {
        excel_cache.sheet_name_for(s): _frame(v) for s, v in series.items() if not v.empty
    }
    old_frames, old_meta = excel_cache.read_cache(cache_path)
    frames = excel_cache.merge_with_previous(new_frames, old_frames)
    meta = _keep_old_meta(meta, old_meta, set(new_frames))
    excel_cache.write_cache(cache_path, frames, meta)
    return meta


def _keep_old_meta(meta: pd.DataFrame, old_meta: pd.DataFrame, fresh: set[str]) -> pd.DataFrame:
    """Series lỗi lần này nhưng có bản cũ: giữ dòng meta cũ (ghi thêm lỗi mới)."""
    if old_meta.empty:
        return meta
    stale = old_meta[~old_meta["sheet"].isin(fresh)].set_index("series_id")
    errors = meta.set_index("series_id")["error"]
    stale["error"] = errors.reindex(stale.index).fillna(stale["error"])
    current = meta[meta["sheet"].isin(fresh)]
    return pd.concat([current, stale.reset_index()], ignore_index=True)


def load_vbma_series(cache_path: Path = DEFAULT_CACHE) -> pd.DataFrame:
    """Cache VBMA thành long store [series_id, date, value, source='VBMA']."""
    frames, meta = excel_cache.read_cache(cache_path)
    sheet_to_id = dict(zip(meta["sheet"], meta["series_id"], strict=True)) if not meta.empty else {}
    parts = [
        df[["date", "value"]].assign(series_id=sheet_to_id.get(sheet, sheet))
        for sheet, df in frames.items()
        if {"date", "value"} <= set(df.columns)
    ]
    if not parts:
        return finalize_store(pd.DataFrame(), SOURCE)
    return finalize_store(pd.concat(parts, ignore_index=True), SOURCE)
