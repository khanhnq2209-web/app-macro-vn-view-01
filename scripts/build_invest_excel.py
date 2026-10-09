"""Xuất file Excel: kênh đầu tư, Fed vs NHNN, tín dụng & GDP, dự trữ ngoại hối & XNK, LDR khu vực.

Dạng wide, cột đầu `time`: tháng (YYYY-MM) hoặc quý (YYYY-Qn). Dữ liệu local (data/raw, data/app/series.parquet,
data/cache) + CSV tra cứu web trong thư mục --web.
Chạy: .venv/Scripts/python scripts/build_invest_excel.py --web <thư mục CSV> --out reports/kenh_dau_tu_vi_mo.xlsx
"""

import argparse
from pathlib import Path

import pandas as pd
from openpyxl.comments import Comment
from openpyxl.styles import PatternFill

RAW = Path("data/raw")
LDR_NOTES: dict[tuple[str, str], str] = {}
VN_NOTES: dict[
    tuple[str, str], str
] = {}  # (quý, credit|tckt|dancu|total) → nguồn số web  # (quý, nước) → nguồn của ô điền từ tin tức
OZ_TO_LUONG = 37.5 / 31.1035  # 1 lượng = 37,5 g; 1 troy oz = 31,1035 g
START = "2010-01"


def series(code: str) -> pd.Series:
    s = pd.read_parquet("data/app/series.parquet")
    s = s[s.code == code].set_index("date")["value"].sort_index()
    return s[~s.index.duplicated(keep="last")]


def monthly(s: pd.Series, how: str = "last") -> pd.Series:
    """Về kỳ tháng (PeriodIndex M): giá trị cuối tháng hoặc bình quân tháng."""
    s = s.dropna()
    s.index = pd.to_datetime(s.index).to_period("M")
    return s.groupby(level=0).agg(how)


def quarterly(s: pd.Series) -> pd.Series:
    s = s.dropna()
    s.index = pd.to_datetime(s.index).to_period("Q")
    return s.groupby(level=0).last()


def yoy(s: pd.Series, lag: int) -> pd.Series:
    """% so cùng kỳ; chỉ tính khi đúng kỳ cách `lag` có số (không lấp)."""
    s = s.asfreq(s.index.freq) if hasattr(s.index, "freq") else s
    full = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq=s.index.freq))
    return ((full / full.shift(lag) - 1) * 100).reindex(s.index)


def targets_actual(label: str) -> pd.Series:
    m = pd.read_excel(RAW / "28.1_Muc-tieu-Chinh-phu.xlsx")
    row = m[m["Chỉ tiêu (gộp cấp)"] == f"{label} - Thực hiện"].iloc[0, 2:]
    return pd.to_numeric(row, errors="coerce").rename(lambda y: int(y)).dropna()


def gdp_real_yoy() -> pd.Series:
    """Tăng trưởng GDP thực theo quý: VBMA công bố (2017+), trước đó tự tính (trước điểm gãy 2021)."""
    return quarterly(series("gdp_yoy_published")).combine_first(
        quarterly(series("gdp_yoy").loc[:"2016"])
    )


def web_csv(web: Path, name: str) -> pd.DataFrame | None:
    p = web / name
    return pd.read_csv(p) if p.exists() else None


def month_index(end) -> pd.PeriodIndex:
    return pd.period_range(START, end, freq="M")


def finish(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(axis=0, how="all", subset=[c for c in df.columns if c != "Ghi chú"])
    df.index = df.index.astype(str)
    return df.rename_axis("time").reset_index()


# ---------- Sheet 1: kênh đầu tư (tháng) ----------
def channel_levels(web: Path) -> pd.DataFrame:
    vcb = pd.read_excel(RAW / "20_Ty gia VCB.xlsx")
    usd_vcb = monthly(vcb[vcb.ma_ngoai_te == "USD"].groupby("ngay")["ban"].last())
    fx_c = monthly(series("fx_central"))
    gold = monthly(
        pd.read_excel("data/cache/yahoo.xlsx", sheet_name="GC=F").groupby("date")["close"].last()
    )
    usd_for_gold = usd_vcb.combine_first(fx_c)  # VCB từ 2015, trước đó tỷ giá trung tâm/BQLNH

    df = pd.DataFrame(index=month_index(gold.index.max()))
    w = web_csv(web, "web_gold_vnindex_monthly.csv")
    if w is not None:
        w.index = pd.PeriodIndex(w["time"], freq="M")
        df["Vàng SJC bán (VND/lượng)"] = w["sjc_sell_vnd_luong"]
    else:
        df["Vàng SJC bán (VND/lượng)"] = None
    df["Vàng thế giới (USD/oz)"] = gold
    # tỷ giá chưa có tháng mới nhất → dùng tỷ giá gần nhất
    df["Vàng thế giới quy đổi (VND/lượng)"] = (
        gold * usd_for_gold.reindex(df.index).ffill() * OZ_TO_LUONG
    )
    df["Chênh SJC - thế giới (VND/lượng)"] = (
        df["Vàng SJC bán (VND/lượng)"] - df["Vàng thế giới quy đổi (VND/lượng)"]
    )
    df["USD/VND VCB bán"] = usd_vcb
    df["USD/VND tỷ giá trung tâm"] = fx_c
    df["VN-Index"] = w["vnindex_close"] if w is not None else None
    df["LS tiết kiệm 12T Big4 BQ tháng (%)"] = monthly(series("deposit_12m_big4"), "mean")
    r = web_csv(web, "web_deposit_wb.csv")
    if r is not None:  # số năm, gán cho mọi tháng trong năm
        df["LS tiền gửi BQ năm - WB (%)"] = (
            r.set_index("time")["deposit_rate_wb_pct"].reindex(df.index.year).to_numpy()
        )
    return df.astype(float)


def sheet_kenh_dau_tu(web: Path) -> pd.DataFrame:
    df = channel_levels(web)
    for col, name in [
        ("Vàng SJC bán (VND/lượng)", "vàng SJC"),
        ("Vàng thế giới quy đổi (VND/lượng)", "vàng thế giới tính VND"),
        ("USD/VND VCB bán", "USD VCB"),
        ("USD/VND tỷ giá trung tâm", "USD tỷ giá trung tâm"),
        ("VN-Index", "VN-Index"),
    ]:
        df[f"LN 12 tháng {name} (%)"] = yoy(df[col], 12)
    # gửi 12T từ 12 tháng trước → lãi nhận được trong 12 tháng tới kỳ này
    dep = df["LS tiết kiệm 12T Big4 BQ tháng (%)"]
    if (
        "LS tiền gửi BQ năm - WB (%)" in df
    ):  # trước 2016 chưa có Big4 → dùng LS tiền gửi BQ năm của WB
        dep = dep.combine_first(df["LS tiền gửi BQ năm - WB (%)"])
    df["LN 12 tháng tiết kiệm (%)"] = dep.shift(12)

    m2 = pd.read_excel(RAW / "04_money supply.xlsx").set_index("Ngày")["Cung tiền M2"]
    credit = pd.read_excel(RAW / "05_credit growth.xlsx").set_index("Ngày (date)")["Tín dụng"]
    gdp = gdp_real_yoy()
    df["CPI so cùng kỳ (%)"] = monthly(series("cpi_yoy"))
    df["M2 (tỷ VND)"] = monthly(m2)
    df["Tăng trưởng M2 so cuối năm trước (%)"] = monthly(series("m2_ytd"))
    df["Tăng trưởng M2 so cùng kỳ (%)"] = yoy(df["M2 (tỷ VND)"], 12)
    df["Dư nợ tín dụng (tỷ VND)"] = monthly(credit)
    df["Tăng trưởng tín dụng so cuối năm trước (%)"] = monthly(series("credit_ytd"))
    df["Tăng trưởng tín dụng so cùng kỳ (%)"] = monthly(series("credit_yoy"))
    df["Tăng trưởng GDP thực so cùng kỳ (quý, %)"] = pd.Series(
        gdp.values, index=gdp.index.asfreq("M", "end")
    )
    return finish(df)


def sheet_kenh_dau_tu_nam(web: Path) -> pd.DataFrame:
    """Tổng hợp năm: lợi nhuận cả năm từng kênh (cuối năm so cuối năm trước) + vĩ mô."""
    lv = channel_levels(web)
    y = lv.groupby(lv.index.year).last()
    w = web_csv(web, "web_gold_vnindex.csv")
    if w is not None:  # bổ sung giá cuối năm từ bảng năm nếu thiếu tháng 12
        w = w.set_index("time")
        y["Vàng SJC bán (VND/lượng)"] = y["Vàng SJC bán (VND/lượng)"].combine_first(
            w["sjc_sell_vnd_luong"]
        )
        y["VN-Index"] = y["VN-Index"].combine_first(w["vnindex_close"])
    out = pd.DataFrame(index=y.index)
    out["Kỳ cuối"] = lv.index.to_series().groupby(lv.index.year).last().astype(str)
    for col, name in [
        ("Vàng SJC bán (VND/lượng)", "vàng SJC"),
        ("Vàng thế giới quy đổi (VND/lượng)", "vàng thế giới tính VND"),
        ("USD/VND VCB bán", "USD VCB"),
        ("USD/VND tỷ giá trung tâm", "USD tỷ giá trung tâm"),
        ("VN-Index", "VN-Index"),
    ]:
        out[col] = y[col]
        out[f"LN {name} (%)"] = (y[col] / y[col].shift(1) - 1) * 100
    dep = lv["LS tiết kiệm 12T Big4 BQ tháng (%)"]
    if "LS tiền gửi BQ năm - WB (%)" in lv:
        dep = dep.combine_first(lv["LS tiền gửi BQ năm - WB (%)"])
    out["LN tiết kiệm 12T (LS BQ năm, %)"] = dep.groupby(dep.index.year).mean()
    out["CPI bình quân (%)"] = targets_actual("CPI bình quân")
    out["Tăng trưởng GDP thực (%)"] = targets_actual("Tăng trưởng GDP")
    m2 = monthly(series("m2_ytd"))
    cr = monthly(series("credit_ytd"))
    out["Tăng trưởng M2 so cuối năm trước (%)"] = m2.groupby(m2.index.year).last()
    out["Tăng trưởng tín dụng so cuối năm trước (%)"] = cr.groupby(cr.index.year).last()
    out = out.loc[2010:]
    out["Ghi chú"] = None
    out.loc[out.index.max(), "Ghi chú"] = (
        f"Năm dở dang: giá đến {out['Kỳ cuối'].iloc[-1]}, M2 đến {m2.index.max()}, tín dụng đến {cr.index.max()}"
    )
    return out.rename_axis("time").reset_index()


# ---------- Sheet 2: Fed vs tái cấp vốn (tháng) ----------
def sheet_fed_vs_nhnn(web: Path) -> pd.DataFrame:
    sbv = pd.read_excel(RAW / "06_LS sbv.xlsx")
    sbv.columns = sbv.columns.str.strip()
    sbv = sbv.set_index("Ngày").sort_index()
    m = pd.DataFrame(
        {
            "Fed - cận trên (%)": monthly(series("fed_upper")),
            "Fed - cận dưới (%)": monthly(series("fed_lower")),
            "Fed - EFFR (%)": monthly(series("effr")),
            "NHNN - LS tái cấp vốn (%)": monthly(sbv["Lãi suất tái cấp vốn"] * 100),
            "NHNN - LS tái chiết khấu (%)": monthly(sbv["Lãi suất tái chiết khấu"] * 100),
        }
    )
    w = web_csv(web, "web_sbv_rates_monthly.csv")
    if w is not None:  # file local từ 01/2016; trước đó lấy số tra cứu web
        w.index = pd.PeriodIndex(w["time"], freq="M")
        m = m.reindex(m.index.union(w.index))
        m["NHNN - LS tái cấp vốn (%)"] = m["NHNN - LS tái cấp vốn (%)"].combine_first(
            w["refi_rate_pct"]
        )
        m["NHNN - LS tái chiết khấu (%)"] = m["NHNN - LS tái chiết khấu (%)"].combine_first(
            w["rediscount_rate_pct"]
        )
    m = m.ffill().loc[START:]
    m["Chênh tái cấp vốn - Fed cận trên (điểm %)"] = (
        m["NHNN - LS tái cấp vốn (%)"] - m["Fed - cận trên (%)"]
    )
    return finish(m)


# ---------- Sheet 3: tín dụng & GDP (quý) ----------
def sheet_tin_dung_gdp(web: Path) -> pd.DataFrame:
    c = pd.read_excel(RAW / "05_credit growth.xlsx").set_index("Ngày (date)").sort_index()
    sectors = [
        "Tín dụng",
        "Nông, lâm, thủy sản",
        "Công nghiệp",
        "Xây dựng",
        "Thương mại",
        "Vận tải, viễn thông",
        "Khác",
    ]
    g = (
        pd.read_excel(RAW / "GDP-hien-hanh.xlsx")
        .set_index("Chỉ tiêu")
        .loc["GDP theo giá hiện hành"]
        .astype(float)
    )
    g.index = pd.PeriodIndex([f"{c_[3:]}Q{c_[1]}" for c_ in g.index], freq="Q")

    q = pd.DataFrame(
        index=pd.period_range(
            "2010Q1", max(g.index.max(), quarterly(c["Tín dụng"]).index.max()), freq="Q"
        )
    )
    ws = web_csv(
        web, "web_credit_sector.csv"
    )  # dư nợ theo ngành trước 2018 (file local từ 01/2018)
    web_cols = dict(
        zip(
            sectors[1:],
            [
                "nong_lam_thuy_san",
                "cong_nghiep",
                "xay_dung",
                "thuong_mai",
                "van_tai_vien_thong",
                "khac",
            ],
            strict=True,
        )
    )
    if ws is not None:
        ws.index = pd.PeriodIndex(ws["time"], freq="M").asfreq("Q")
        ws = ws[~ws.index.duplicated(keep="last")]
    for s in sectors:
        name = "Dư nợ tín dụng toàn nền KT" if s == "Tín dụng" else f"Dư nợ - {s}"
        col = quarterly(c[s])
        if ws is not None and s in web_cols:
            col = col.combine_first(
                pd.to_numeric(ws[web_cols[s]], errors="coerce").dropna().loc[:"2017Q4"]
            )
        q[f"{name} (tỷ VND)"] = col
    total = q["Dư nợ tín dụng toàn nền KT (tỷ VND)"]
    q["Tăng trưởng dư nợ so cùng kỳ (tính từ số dư, %)"] = yoy(total, 4)
    q["Tăng trưởng tín dụng so cuối năm trước (công bố, %)"] = quarterly(series("credit_ytd"))
    q["Tăng trưởng tín dụng so cùng kỳ (công bố, %)"] = quarterly(series("credit_yoy"))
    q["GDP danh nghĩa quý (tỷ VND)"] = g
    q["GDP danh nghĩa 4 quý gần nhất (tỷ VND)"] = g.rolling(4).sum()
    # File 2010–2020 là gốc cũ (trước đánh giá lại quy mô GDP) → nhân hệ số = GDP năm WB / tổng 4 quý file
    wb = web_csv(web, "web_gdp_wb.csv").set_index("time")["gdp_nominal_bn_vnd"]
    year_sum = g.groupby(g.index.year).sum()
    factor = (wb / year_sum).loc[:2020].reindex(g.index.year).fillna(1.0).to_numpy()
    g_adj = g * factor
    q["Hệ số điều chỉnh gốc GDP"] = pd.Series(factor, index=g.index)
    q["GDP danh nghĩa quý - gốc mới (tỷ VND)"] = g_adj
    q["GDP danh nghĩa 4 quý gần nhất - gốc mới (tỷ VND)"] = g_adj.rolling(4).sum()
    q["GDP danh nghĩa năm - World Bank (tỷ VND)"] = pd.Series(
        wb.values, index=pd.PeriodIndex([f"{y}Q4" for y in wb.index], freq="Q")
    )
    # 2021 so với quý 2020 đã điều chỉnh: cơ cấu quý gốc cũ khác gốc mới → không so được, để trống
    q["Tăng trưởng GDP danh nghĩa so cùng kỳ - gốc mới (%)"] = yoy(g_adj, 4).mask(
        g_adj.index.year == 2021
    )
    q["Tăng trưởng GDP thực so cùng kỳ (%)"] = gdp_real_yoy()
    q["Dư nợ tín dụng / GDP 4 quý - gốc mới (%)"] = (
        total / q["GDP danh nghĩa 4 quý gần nhất - gốc mới (tỷ VND)"] * 100
    )
    q["Dư nợ tín dụng / GDP 4 quý - số file gốc (%)"] = (
        total / q["GDP danh nghĩa 4 quý gần nhất (tỷ VND)"] * 100
    )
    nhnn = targets_actual("Tăng trưởng tín dụng (định hướng NHNN)")
    q["Tăng trưởng tín dụng cả năm - NHNN công bố (%)"] = pd.Series(
        nhnn.values, index=pd.PeriodIndex([f"{y}Q4" for y in nhnn.index], freq="Q")
    )
    return finish(q)


# ---------- Sheet 4: dự trữ ngoại hối & XNK (tháng) ----------
def sheet_du_tru_xnk(web: Path) -> pd.DataFrame:
    x = pd.read_excel(RAW / "18_XNK.xlsx").set_index("Ngày").sort_index()
    df = pd.DataFrame(index=month_index(x.index.max().to_period("M")))
    df["Xuất khẩu (tỷ USD)"] = monthly(x["Xuất khẩu Tổng"]) / 1000
    df["Nhập khẩu (tỷ USD)"] = monthly(x["Nhập khẩu Tổng"]) / 1000
    df["Cán cân thương mại (tỷ USD)"] = df["Xuất khẩu (tỷ USD)"] - df["Nhập khẩu (tỷ USD)"]
    df["Cán cân thương mại lũy kế 12 tháng (tỷ USD)"] = (
        df["Cán cân thương mại (tỷ USD)"].rolling(12).sum()
    )
    df["Nhập khẩu 12 tháng gần nhất (tỷ USD)"] = df["Nhập khẩu (tỷ USD)"].rolling(12).sum()

    res = pd.Series(dtype=float)
    src = pd.Series(dtype=object)
    wm = web_csv(web, "web_fx_reserves_monthly.csv")
    if wm is not None:
        wm.index = pd.PeriodIndex(wm["time"], freq="M")
        res = wm["reserves_bn_usd"].dropna()
        src = wm["source"].reindex(res.index)
        excl = wm["reserves_excl_gold_bn_usd"]
    wa = web_csv(web, "web_fx_reserves.csv")
    if wa is not None:  # bổ sung điểm cuối năm / điểm mới nhất từ bảng năm
        wa.index = pd.PeriodIndex(pd.to_datetime(wa["date"]), freq="M")
        ann = wa["reserves_bn_usd"].combine_first(wa["reserves_alt_bn_usd"]).dropna()
        add = ann[~ann.index.isin(res.index)]
        res = pd.concat([res, add]).sort_index()
        src = pd.concat(
            [
                src,
                wa["source"]
                .where(wa["reserves_bn_usd"].notna(), wa["source_alt"])
                .reindex(add.index),
            ]
        )
        df["Số tháng NK - WB công bố (hàng hóa & dịch vụ)"] = wa["months_import_published"]
    df = df.reindex(df.index.union(res.index))
    df["Dự trữ ngoại hối gồm vàng (tỷ USD)"] = res
    if wm is not None:
        df["Dự trữ ngoại hối không gồm vàng (tỷ USD)"] = excl
    df["Dự trữ / số tháng nhập khẩu (tháng)"] = res / (
        df["Nhập khẩu 12 tháng gần nhất (tỷ USD)"] / 12
    )
    df["Nguồn dự trữ"] = src.reindex(df.index)
    return finish(df)


# ---------- Sheet 5: LDR ----------
def sheet_ldr(web: Path) -> pd.DataFrame:
    q = web_csv(web, "web_ldr_quarterly.csv")
    df = (
        q
        if q is not None and q.drop(columns="time").notna().any().any()
        else web_csv(web, "web_ldr.csv")
    )
    df = df.set_index("time")
    lt = web_csv(web, "web_ldr_latest.csv")
    if lt is not None:  # số mới từ tin tức/NHTW; ghi nguồn vào comment từng ô
        lt = lt.dropna(subset=["ldr_pct"])
        lt = lt[~lt["definition"].str.contains("listed", case=False)]  # chỉ nhóm NH niêm yết → bỏ
        # cùng định nghĩa với chuỗi chính: PBoC (Trung Quốc), LDR toàn hệ thống NHNN (VN) → điền vào ô trống của cột nước
        same = (lt["country"] == "China") | (
            (lt["country"] == "Vietnam") & lt["definition"].str.startswith("simple")
        )
        lt["col"] = lt["country"].where(same, lt["country"] + " - nguồn quốc gia")
        lt["q"] = pd.PeriodIndex(lt["time"], freq="M").asfreq("Q").strftime("%Y-Q%q")
        lt = lt.sort_values("time").groupby(["q", "col"]).last()
        df = df.reindex(df.index.union(lt.index.get_level_values(0).unique()))
        for (q, col), r in lt.iterrows():
            if col not in df:
                df[col] = float("nan")
            if pd.isna(df.loc[q, col]):
                df.loc[q, col] = r["ldr_pct"]
                LDR_NOTES[(q, col)] = (
                    f"{r['source']} ({r['time']}). {r['definition']}. {r['note'] if pd.notna(r['note']) else ''} {r['url']}"
                )
        df = df[
            sorted(df.columns, key=lambda c: (c.split(" - ")[0] != "Vietnam", c.split(" - ")[0], c))
        ]
    df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
    df = df.join(vn_credit_deposit(web), how="outer").loc["2010-Q1":]
    return df.rename_axis("time").reset_index()


VN_LDR_COLS = [
    "VN - Dư nợ tín dụng (tỷ VND)",
    "VN - Tiền gửi TCKT (tỷ VND)",
    "VN - Tiền gửi dân cư (tỷ VND)",
    "VN - Tổng huy động (tỷ VND)",
]


def vn_credit_deposit(web: Path) -> pd.DataFrame:
    """Dư nợ & huy động VN theo quý (giá trị tháng cuối có số trong quý). Local trước, web bù."""
    m = pd.read_excel(RAW / "04_money supply.xlsx").set_index("Ngày")
    c = pd.read_excel(RAW / "05_credit growth.xlsx").set_index("Ngày (date)")["Tín dụng"]
    loc = pd.DataFrame(
        {
            "credit": monthly(c),
            "tckt": monthly(m["Tiền gửi TCKT"]),
            "dancu": monthly(m["Tiền gửi dân cư"]),
        }
    )
    loc["total"] = loc["tckt"] + loc["dancu"]
    for f in [
        "dlkt_credit_deposit.csv",
        "web_vn_credit_deposit.csv",
    ]:  # API dulieukinhte trước, tin tức sau
        w = web_csv(web, f)
        if w is None:
            continue
        w.index = pd.PeriodIndex(w["time"], freq="M")
        w = w.rename(
            columns={
                "credit_total": "credit",
                "deposit_tckt": "tckt",
                "deposit_dancu": "dancu",
                "deposit_total": "total",
            }
        )
        w = w[~w.index.duplicated(keep="last")]
        for per, r in w.iterrows():
            for k in ["credit", "tckt", "dancu", "total"]:
                if pd.notna(r[k]) and (
                    per not in loc.index or pd.isna(loc.loc[per, k] if per in loc.index else None)
                ):
                    loc.loc[per, k] = r[k]
                    VN_NOTES[(per.asfreq("Q").strftime("%Y-Q%q"), k)] = (
                        f"{r['source']} ({per}). {r['url']}"
                    )
    loc = loc.sort_index()
    q = loc.groupby(loc.index.asfreq("Q")).last()  # tháng cuối có số trong quý
    both = loc.dropna(
        subset=["credit", "total"]
    )  # có cả dư nợ và huy động → lấy cùng một tháng để LDR khớp kỳ
    q.update(both.groupby(both.index.asfreq("Q")).last())
    q.index = q.index.strftime("%Y-Q%q")
    q.columns = VN_LDR_COLS
    return q.dropna(how="all")


SOURCES = [
    ("1_Kenh_dau_tu", "Vàng SJC, VN-Index", "Tra cứu web (bảng nguồn bên dưới), giá cuối tháng"),
    (
        "1_Kenh_dau_tu",
        "Vàng thế giới",
        "Yahoo Finance GC=F cuối tháng; VND/lượng = USD/oz × USD VCB bán (trước 2015: tỷ giá trung tâm) × 37,5/31,1035",
    ),
    (
        "1_Kenh_dau_tu",
        "USD",
        "VCB giá bán (data/raw/20, từ 2015); tỷ giá trung tâm NHNN (data/raw/19)",
    ),
    (
        "1_Kenh_dau_tu",
        "Tiết kiệm",
        "LS 12 tháng BQ 4 NH Big4, bình quân tháng (Simplize, từ 2016); trước 2016 dùng LS tiền gửi BQ năm World Bank FR.INR.DPST (định nghĩa khác, mọi kỳ hạn). LN 12 tháng = LS của 12 tháng trước",
    ),
    (
        "1_Kenh_dau_tu",
        "LN 12 tháng",
        "% thay đổi so với cùng tháng năm trước (mua 12 tháng trước, bán kỳ này)",
    ),
    (
        "1_Kenh_dau_tu",
        "M2, tín dụng, CPI, GDP",
        "dulieukinhte/VBMA (data/raw/04, 05, series.parquet). GDP thực theo quý gắn vào tháng cuối quý. Lưu ý: M2 so cuối năm từ 10/2025 nghi lỗi nguồn; tín dụng T2=T3/2026 lặp số",
    ),
    (
        "1b_Kenh_dau_tu_nam",
        "Tổng hợp năm",
        "Cuối năm so cuối năm trước; CPI BQ, GDP thực năm từ Mục tiêu-Thực hiện Chính phủ (data/raw/28.1)",
    ),
    ("2_Fed_vs_NHNN", "Fed", "FRED DFEDTARU/DFEDTARL/EFFR, cuối tháng"),
    (
        "2_Fed_vs_NHNN",
        "NHNN",
        "LS tái cấp vốn, tái chiết khấu cuối tháng: data/raw/06 từ 01/2016; trước đó tra cứu web (lịch sử quyết định NHNN / IMF)",
    ),
    (
        "3_Tin_dung_GDP",
        "Dư nợ",
        "data/raw/05 (tỷ VND, cuối quý; theo ngành từ 2018, trước 2018 tra cứu web nếu có — phân ngành có thể khác). Tăng trưởng tính từ số dư lệch với % công bố — giữ cả hai",
    ),
    (
        "3_Tin_dung_GDP",
        "GDP",
        "GDP giá hiện hành theo quý (data/raw/GDP-hien-hanh); tín dụng/GDP = dư nợ cuối quý / GDP 4 quý gần nhất",
    ),
    (
        "3_Tin_dung_GDP",
        "GDP gốc mới",
        "[ước tính] File 2010–2020 là gốc cũ (trước đánh giá lại quy mô GDP, 2021 nhảy ~33%). Quý 2010–2020 × hệ số = GDP năm World Bank (NY.GDP.MKTP.CN, đã đánh giá lại) / tổng 4 quý file. 2021+ giữ nguyên. Tăng trưởng danh nghĩa so cùng kỳ các quý 2021 để trống (cơ cấu quý 2 gốc khác nhau)",
    ),
    ("4_Du_tru_XNK", "XNK", "data/raw/18 (triệu USD/tháng → tỷ USD)"),
    (
        "4_Du_tru_XNK",
        "Dự trữ ngoại hối",
        "IMF International Liquidity (api.imf.org): gồm vàng (định giá theo giá NHNN, TRGNV_REVS) và không gồm vàng (RXF11_REVS). Số tháng NK tính từ chuỗi gồm vàng. Số tháng NK = dự trữ / (NK hàng hóa 12 tháng gần nhất / 12); WB tính cả dịch vụ nên thấp hơn",
    ),
    (
        "5_LDR_khu_vuc",
        "LDR",
        "Cột tên nước: IMF FSI (LDR = 10000 / tiền gửi khách hàng trên cho vay), riêng Trung Quốc = PBoC, Singapore = MAS. Ô tô vàng: số từ tin tức/NHTW (comment trong ô ghi nguồn + link). Chỉ điền thẳng vào cột nước khi cùng định nghĩa (Trung Quốc PBoC, VN toàn hệ thống); nước khác để cột '- nguồn quốc gia' vì định nghĩa khác IMF. Chi tiết nguồn ở bảng dưới",
    ),
    (
        "5_LDR_khu_vuc",
        "VN tự tính",
        "Dư nợ (data/raw/05) / (Tiền gửi TCKT + dân cư, data/raw/04, từ 12/2018); quý = tháng cuối trong quý có đủ cả dư nợ và huy động. Ô tô vàng = số tra cứu web (comment ghi nguồn). Cột LDR tự tính là công thức Excel. Từ 10/2025 nguồn phân loại lại tiền gửi TCKT ↔ dân cư (từng cấu phần gãy, tổng không đổi). Lưu ý dư nợ 2025 trong file nghi cao hơn thực tế (tăng 20,5% vs công bố 19,07%)",
    ),
]


def style_ldr(ws, df5: pd.DataFrame) -> None:
    """Comment nguồn + tô vàng ô điền từ web; cột LDR VN tự tính bằng công thức Excel."""
    for (q, country), note in LDR_NOTES.items():
        cell = ws.cell(
            row=df5.index[df5["time"] == q][0] + 2, column=df5.columns.get_loc(country) + 1
        )
        cell.comment = Comment(note, "nguồn")
        cell.fill = PatternFill("solid", fgColor="FFF2CC")
    key = dict(zip(["credit", "tckt", "dancu", "total"], VN_LDR_COLS, strict=True))
    for (q, k), note in VN_NOTES.items():
        if (df5["time"] == q).any():
            cell = ws.cell(
                row=df5.index[df5["time"] == q][0] + 2, column=df5.columns.get_loc(key[k]) + 1
            )
            cell.comment = Comment(note, "nguồn")
            cell.fill = PatternFill("solid", fgColor="FFF2CC")
    cc = ws.cell(
        row=1, column=ws.max_column + 1, value="VN - LDR tự tính = dư nợ / tổng huy động (%)"
    )
    col_cr = ws.cell(row=1, column=df5.columns.get_loc(VN_LDR_COLS[0]) + 1).column_letter
    col_dep = ws.cell(row=1, column=df5.columns.get_loc(VN_LDR_COLS[3]) + 1).column_letter
    for r in range(2, ws.max_row + 1):
        ws.cell(
            row=r,
            column=cc.column,
            value=f'=IF(AND(ISNUMBER({col_cr}{r}),ISNUMBER({col_dep}{r})),{col_cr}{r}/{col_dep}{r}*100,"")',
        ).number_format = "0.0"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("reports/kenh_dau_tu_vi_mo.xlsx"))
    a = ap.parse_args()

    sheets = {
        "1_Kenh_dau_tu": sheet_kenh_dau_tu(a.web),
        "1b_Kenh_dau_tu_nam": sheet_kenh_dau_tu_nam(a.web),
        "2_Fed_vs_NHNN": sheet_fed_vs_nhnn(a.web),
        "3_Tin_dung_GDP": sheet_tin_dung_gdp(a.web),
        "4_Du_tru_XNK": sheet_du_tru_xnk(a.web),
        "5_LDR_khu_vuc": sheet_ldr(a.web),
    }
    src = pd.DataFrame(SOURCES, columns=["Sheet", "Chỉ tiêu", "Nguồn / cách tính"])
    extra = [
        d
        for f in ["web_ldr_sources.csv", "web_ldr_latest.csv"]
        if (d := web_csv(a.web, f)) is not None
    ]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(a.out, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
        src.to_excel(xw, sheet_name="Nguon_ghi_chu", index=False)
        row = len(src) + 3
        for e in extra:
            e.to_excel(xw, sheet_name="Nguon_ghi_chu", index=False, startrow=row)
            row += len(e) + 3
        style_ldr(xw.book["5_LDR_khu_vuc"], sheets["5_LDR_khu_vuc"])
        for ws in xw.book.worksheets:
            ws.freeze_panes = "B2"
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(
                    max(len(str(col[0].value or "")), 10) + 2, 45
                )
                for cell in col[1:]:
                    if isinstance(cell.value, float):
                        cell.number_format = "#,##0.00" if abs(cell.value) < 1000 else "#,##0"
    print(f"Đã ghi {a.out}")
    for name, df in sheets.items():
        print(name, df.shape, df["time"].iloc[0], "→", df["time"].iloc[-1])


if __name__ == "__main__":
    main()
