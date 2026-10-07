"""Đối chiếu số của app với nguồn độc lập. Chạy: python scripts/verify_numbers.py

Chỉ in bảng tổng hợp: số kỳ trùng, lệch lớn nhất, kỳ lệch nhiều nhất của từng phép kiểm.
"""

from __future__ import annotations

import sys

import pandas as pd
import requests

from macro_app.io import vbma, vn_raw
from macro_app.paths import APP_DIR, RAW_DIR

HEATMAP_URL = "https://vbma.org.vn/csv/markets/tables/vi/tong_quan_kinh_te_vi_mo.csv"
TOL = 0.15  # điểm %; VBMA làm tròn 1 chữ số thập phân


def app_series(code: str) -> pd.Series:
    s = pd.read_parquet(APP_DIR / "series.parquet")
    part = s[s["code"] == code]
    return pd.Series(part["value"].to_numpy(), index=pd.DatetimeIndex(part["date"]))


def compare(name: str, ours: pd.Series, ref: pd.Series, tol: float = TOL) -> dict:
    d = pd.concat({"ours": ours, "ref": ref}, axis=1).dropna()
    diff = (d["ours"] - d["ref"]).abs()
    bad = diff[diff > tol]
    return {
        "kiểm tra": name,
        "số kỳ trùng": len(d),
        "lệch lớn nhất": round(diff.max(), 3) if len(d) else None,
        "số kỳ lệch > ngưỡng": len(bad),
        "kỳ lệch nhiều nhất": diff.idxmax().strftime("%m/%Y") if len(bad) else "",
        "kỳ cuối": d.index.max().strftime("%m/%Y") if len(d) else "",
    }


def heatmap_rows() -> dict[str, pd.Series]:
    resp = requests.get(HEATMAP_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    table = vbma.decode_csv(resp.content)
    labels = table.iloc[:, 0].astype(str).str.strip().tolist()
    out = {}
    for key, label in {
        "credit": "Tăng trưởng tín dụng",
        "construction": "Xây dựng",
        "m2": "Cung tiền M2",
        "fdi": "FDI đăng kí",
        "cpi": "Lạm phát",
    }.items():
        if label in labels:
            out[key] = vbma.row_series(table, labels.index(label), 2)
    return out


def ytd_from_level(level: pd.Series) -> pd.Series:
    level = level.dropna()
    dec = level[level.index.month == 12]
    base = pd.Series(level.index.year - 1, index=level.index).map(
        pd.Series(dec.to_numpy(), index=dec.index.year)
    )
    return (level / base - 1) * 100


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    vn = vn_raw.load_vn_series()

    def raw(sid: str) -> pd.Series:
        part = vn[vn["series_id"] == sid]
        return pd.Series(part["value"].to_numpy(), index=pd.DatetimeIndex(part["date"]))

    heat = heatmap_rows()
    rows = [
        compare(
            "Tín dụng YTD vs VBMA",
            app_series("credit_ytd"),
            heat.get("credit", pd.Series(dtype=float)),
        ),
        compare(
            "Tín dụng xây dựng YTD vs VBMA",
            app_series("credit_construction_ytd"),
            heat.get("construction", pd.Series(dtype=float)),
        ),
        compare("M2 YTD vs VBMA", app_series("m2_ytd"), heat.get("m2", pd.Series(dtype=float))),
        compare(
            "CPI YoY (app) vs VBMA", app_series("cpi_yoy"), heat.get("cpi", pd.Series(dtype=float))
        ),
        compare(
            "FDI lũy kế YoY vs VBMA",
            app_series("fdi_registered_ytd_yoy"),
            heat.get("fdi", pd.Series(dtype=float)),
            tol=1.0,
        ),
        compare(
            "Tín dụng YTD: cột % vs tính từ dư nợ",
            app_series("credit_ytd"),
            ytd_from_level(raw("vn.credit_level")),
        ),
        compare(
            "M2 YTD: cột % vs tính từ số dư",
            app_series("m2_ytd"),
            ytd_from_level(raw("vn.m2_level")),
        ),
    ]
    print(pd.DataFrame(rows).to_string(index=False))

    panel, banks = vn_raw.load_deposit_panel(), vn_raw.load_banks()
    big4 = banks.loc[banks["is_big4"], "bank_code"]
    last = panel[(panel["tenor_m"] == 12) & panel["bank_code"].isin(big4)]
    last = last.sort_values("date").groupby("bank_code").tail(1)
    print("\nLS huy động 12 tháng, quote mới nhất của từng NH Big4:")
    print(last[["bank_code", "date", "rate_pct"]].to_string(index=False))
    print(
        "Bình quân:",
        round(last["rate_pct"].mean(), 3),
        "| app:",
        round(app_series("deposit_12m_big4").iloc[-1], 3),
    )
    print("\nFile raw dùng:", len(list(RAW_DIR.glob("*.xlsx"))), "xlsx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
