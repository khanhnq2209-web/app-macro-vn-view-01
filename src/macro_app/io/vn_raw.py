"""Chuỗi Việt Nam từ `data/raw/` thành long store [series_id, date, value, source].

File có sheet wide (xuất từ dulieukinhte) đọc sheet wide vì inbox merge cập nhật sheet này;
file chỉ có `Sheet1` dạng long (04, 05, 06) đọc `Sheet1`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from macro_app.io.wide_sheet import read_wide_sheet
from macro_app.paths import BANKS_FILE, DEPOSIT_FILE, RAW_DIR

SOURCE = "dulieukinhte"
STORE_COLUMNS = ["series_id", "date", "value", "source"]
DEPOSIT_SHEET = "LS Lãi tiền gửi"
GOVBOND_SECONDARY = "Đường cong lợi suất TPCP (thị trường thứ cấp)"


@dataclass(frozen=True)
class WideSource:
    """File có sheet wide: {series_id: (nhãn dòng, nhãn dòng cha hoặc None)}."""

    file: str
    rows: dict[str, tuple[str, str | None]]


@dataclass(frozen=True)
class LongSource:
    """File chỉ có `Sheet1` long: {series_id: tên cột đã strip}."""

    file: str
    columns: dict[str, str]
    scale: float = 1.0
    month_end: bool = False
    ffill_ids: frozenset[str] = field(default_factory=frozenset)


WIDE_SOURCES = [
    WideSource(
        "GDP-So-Sanh.xlsx",
        {
            "vn.gdp_real": ("GDP theo giá so sánh", None),
            "vn.gdp_real_realestate": ("Hoạt động kinh doanh bất động sản", None),
            "vn.gdp_real_construction": ("Xây dựng", None),
            "vn.gdp_real_finance": ("Hoạt động tài chính, ngân hàng và bảo hiểm", None),
        },
    ),
    WideSource(
        "07_CPI.xlsx",
        {
            "vn.cpi_mom": ("CPI", None),
            "vn.cpi_housing_mom": ("Nhà ở và vật liệu xây dựng", None),
        },
    ),
    WideSource(
        "12_Dau tu cong.xlsx",
        {
            "vn.public_investment": ("Tổng", None),
            "vn.public_investment_central": ("Trung ương", None),
            "vn.public_investment_local": ("Địa phương", None),
            "vn.public_investment_moc": ("Bộ Xây dựng", None),
        },
    ),
    WideSource(
        "13_Loi-suat-TPCP.xlsx",
        {
            "vn.govbond_1y": ("1 năm", GOVBOND_SECONDARY),
            "vn.govbond_5y": ("5 năm", GOVBOND_SECONDARY),
            "vn.govbond_10y": ("10 năm", GOVBOND_SECONDARY),
        },
    ),
    WideSource(
        "18_XNK.xlsx",
        {"vn.export_total": ("Xuất - Tổng", None), "vn.import_total": ("Nhập - Tổng", None)},
    ),
    WideSource("19_Ty-gia-trung tam USDVND.xlsx", {"vn.fx_central": ("Trung tâm", None)}),
    WideSource(
        "28.1_Muc-tieu-Chinh-phu.xlsx",
        {
            "vn.target_gdp_growth": ("Tăng trưởng GDP - Mục tiêu", None),
            "vn.target_cpi_avg": ("CPI bình quân - Mục tiêu", None),
            "vn.target_credit_growth": ("Tăng trưởng tín dụng (định hướng NHNN) - Mục tiêu", None),
        },
    ),
    WideSource(
        "Von-FDI-dang-ky-cap-moi.xlsx",
        {"vn.fdi_registered_ytd": ("Vốn đăng ký cấp mới (Triệu USD)", None)},
    ),
]

LONG_SOURCES = [
    LongSource(
        "04_money supply.xlsx",
        {"vn.m2_ytd": "Tăng trưởng Cung tiền M2 so với cuối năm", "vn.m2_level": "Cung tiền M2"},
        month_end=True,
    ),
    LongSource(
        "05_credit growth.xlsx",
        {
            "vn.credit_ytd": "Tăng trưởng tín dụng so với cuối năm",
            "vn.credit_construction_ytd": "Tăng trưởng Xây dựng",
            "vn.credit_level": "Tín dụng",
            "vn.credit_construction_level": "Xây dựng",
        },
        month_end=True,
    ),
    LongSource(
        "06_LS sbv.xlsx",
        {
            "vn.ib_on": "Lãi suất BQ liên NH kỳ hạn qua đêm",
            "vn.ib_1w": "Lãi suất BQ liên NH kỳ hạn 1 tuần",
            "vn.ib_1m": "Lãi suất BQ liên NH kỳ hạn 1 tháng",
            "vn.refi": "Lãi suất tái cấp vốn",
            "vn.rediscount": "Lãi suất tái chiết khấu",
        },
        scale=100.0,  # file lưu 0.045 = 4,5%
        ffill_ids=frozenset({"vn.refi", "vn.rediscount"}),
    ),
]


def _empty_store() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": pd.Series(dtype=str),
            "date": pd.Series(dtype="datetime64[ns]"),
            "value": pd.Series(dtype=float),
            "source": pd.Series(dtype=str),
        }
    )


def _pick_row(long: pd.DataFrame, label: str, parent: str | None, file: str) -> pd.DataFrame:
    mask = long["row_label"].eq(label)
    if parent is not None:
        mask &= long["parent"].eq(parent)
    rows = long.loc[mask, "row_pos"].unique()
    if len(rows) != 1:
        raise ValueError(f"{file}: dòng '{label}' (cha '{parent}') khớp {len(rows)} dòng, cần 1")
    return long[long["row_pos"].eq(rows[0])]


def read_wide_source(spec: WideSource, raw_dir: Path) -> pd.DataFrame:
    long = read_wide_sheet(raw_dir / spec.file)
    parts = [
        _pick_row(long, label, parent, spec.file)[["date", "value"]].assign(series_id=sid)
        for sid, (label, parent) in spec.rows.items()
    ]
    return pd.concat(parts, ignore_index=True)


def read_long_sheet(path: Path) -> pd.DataFrame:
    """`Sheet1` long: cột đầu = ngày (đổi tên `date`), header đã strip."""
    frame = pd.read_excel(path, sheet_name="Sheet1", engine="openpyxl")
    frame.columns = [str(c).strip() for c in frame.columns]
    frame = frame.rename(columns={frame.columns[0]: "date"})
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce", dayfirst=True).dt.normalize()
    return frame.dropna(subset=["date"]).sort_values("date")


def _ffill_to_last_obs(values: pd.Series) -> pd.Series:
    """Điền xuôi trên các ngày của file, không vượt quá quan sát cuối cùng."""
    last = values.last_valid_index()
    if last is None:
        return values
    return values.ffill().loc[:last]


def read_long_source(spec: LongSource, raw_dir: Path) -> pd.DataFrame:
    frame = read_long_sheet(raw_dir / spec.file).set_index("date")
    if spec.month_end:
        frame.index = frame.index + pd.offsets.MonthEnd(0)
    parts = []
    for sid, column in spec.columns.items():
        values = pd.to_numeric(frame[column], errors="coerce") * spec.scale
        if sid in spec.ffill_ids:
            values = _ffill_to_last_obs(values)
        parts.append(values.rename("value").reset_index().assign(series_id=sid))
    return pd.concat(parts, ignore_index=True)


def finalize_store(frame: pd.DataFrame, source: str) -> pd.DataFrame:
    """Chuẩn hóa về hợp đồng store: bỏ NaN, dedupe (series_id, date) giữ bản sau."""
    if frame.empty:
        return _empty_store()
    out = frame.assign(source=source)
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None).dt.normalize()
    out["value"] = pd.to_numeric(out["value"], errors="coerce").astype(float)
    out = out.dropna(subset=["date", "value"])
    out = out.drop_duplicates(["series_id", "date"], keep="last")
    out = out.sort_values(["series_id", "date"]).reset_index(drop=True)
    return out[STORE_COLUMNS].astype({"series_id": str, "source": str})


def load_vn_series(raw_dir: Path = RAW_DIR, errors: dict | None = None) -> pd.DataFrame:
    """Toàn bộ chuỗi `vn.*` từ file raw.

    Mỗi file đọc riêng: 1 file lỗi (vd đổi tên dòng sau khi gộp inbox) chỉ mất chuỗi của file đó.
    """
    jobs = [(s.file, read_wide_source, s) for s in WIDE_SOURCES]
    jobs += [(s.file, read_long_source, s) for s in LONG_SOURCES]
    parts = []
    for file, reader, spec in jobs:
        try:
            parts.append(reader(spec, raw_dir))
        except Exception as exc:
            if errors is not None:
                errors[f"vn:{file}"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    if not parts:
        return _empty_store()
    return finalize_store(pd.concat(parts, ignore_index=True), SOURCE)


def load_deposit_panel(path: Path = DEPOSIT_FILE) -> pd.DataFrame:
    """LS huy động Simplize: [date, bank_code, tenor_m, rate_pct]."""
    raw = pd.read_excel(path, sheet_name=DEPOSIT_SHEET, engine="openpyxl")
    panel = pd.DataFrame(
        {
            "date": pd.to_datetime(raw["ngay_du_lieu"], errors="coerce").dt.normalize(),
            "bank_code": raw["ma_ngan_hang"].astype("string").str.strip(),
            "tenor_m": pd.to_numeric(
                raw["ky_han"].astype("string").str.extract(r"(\d+)")[0], errors="coerce"
            ),
            "rate_pct": pd.to_numeric(raw["lai_suat_pct"], errors="coerce"),
        }
    ).dropna()
    panel = panel.astype({"bank_code": str, "tenor_m": int, "rate_pct": float})
    return panel.sort_values(["date", "bank_code", "tenor_m"]).reset_index(drop=True)


def load_banks(path: Path = BANKS_FILE) -> pd.DataFrame:
    """Danh mục NH: [bank_code, is_big4, is_big10] (cờ = ô có giá trị 1)."""
    raw = pd.read_excel(path, sheet_name="Sheet1", engine="openpyxl")
    raw.columns = [str(c).strip() for c in raw.columns]

    def flag(column: str) -> pd.Series:
        return pd.to_numeric(raw[column], errors="coerce").eq(1)

    return pd.DataFrame(
        {
            "bank_code": raw["ma_ngan_hang"].astype(str).str.strip(),
            "is_big4": flag("Big4"),
            "is_big10": flag("Big 10"),
        }
    )
