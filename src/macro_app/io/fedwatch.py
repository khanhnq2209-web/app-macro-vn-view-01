"""FedWatch (D9): xác suất lãi suất FOMC vào cache `data/cache/fedwatch.xlsx`.

Nguồn: CME QuikStrike và bản tự tính từ ZQ. Nguồn lỗi giữ bản cache cũ, không dừng nguồn kia.
"""

from __future__ import annotations

import csv
import html
import io
import logging
import re
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests

from macro_app.io import excel_cache, fred, yahoo
from macro_app.metrics import fedwatch_calc as calc
from macro_app.paths import CACHE_DIR

log = logging.getLogger(__name__)

DEFAULT_CACHE = CACHE_DIR / "fedwatch.xlsx"
QS_URL = (
    "https://cmegroup-tools.quikstrike.net/User/QuikStrikeView.aspx"
    "?viewitemid=IntegratedFedWatchTool"
)
QS_DOWNLOADS_TARGET = "ctl00$MainContent$ucViewControl_IntegratedFedWatchTool$lbDownloads"
QS_SOURCE = "CME QuikStrike"
QS_REFERER = "https://www.cmegroup.com/"
FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FRED_INPUTS = ["DFEDTARU", "DFEDTARL", "EFFR", "DFF"]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
SHEETS = ["quikstrike", "computed", "fomc_calendar", "zq_prices"]
_HISTORY_KEYS = {
    "quikstrike": ["asof", "meeting_date"],
    "computed": ["asof", "meeting_date"],
    "zq_prices": ["date", "ticker"],
}
_DATE_COLUMNS = ("asof", "meeting_date", "date")
_HIDDEN_INPUT = re.compile(r"<input[^>]*type=\"hidden\"[^>]*>", re.IGNORECASE)
_RANGE = re.compile(r"\((\d+)-(\d+)\)")
_MEETING_HEADER = re.compile(r"History for (\d{1,2} \w{3} \d{4}) Fed meeting")


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    return session


def _quikstrike_session() -> requests.Session:
    """QuikStrike kiểm tra referrer (iframe nhúng trong cmegroup.com); thiếu thì trả trang lỗi."""
    session = _session()
    session.headers["Referer"] = QS_REFERER
    return session


def hidden_fields(page: str) -> dict[str, str]:
    """Các input hidden của form ASP.NET (__VIEWSTATE, __EVENTVALIDATION, ...)."""
    fields = {}
    for tag in _HIDDEN_INPUT.findall(page):
        name = re.search(r'name="([^"]+)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name:
            fields[name.group(1)] = html.unescape(value.group(1)) if value else ""
    return fields


def fetch_quikstrike_csv(session: requests.Session | None = None) -> str:
    """3 request: trang tool, POST tab Downloads, rồi CSV AllMeetings (lịch sử ~250 phiên)."""
    session = session or _quikstrike_session()
    page = session.get(QS_URL, timeout=30)
    page.raise_for_status()
    if "ErrorPage" in page.url:
        raise RuntimeError("QuikStrike từ chối truy cập (trang lỗi)")
    form = hidden_fields(page.text)
    form.update({"__EVENTTARGET": QS_DOWNLOADS_TARGET, "__EVENTARGUMENT": ""})
    downloads = session.post(page.url, data=form, timeout=60)
    downloads.raise_for_status()
    link = re.search(r"Export/FedWatch/AllMeetings\.aspx\?[^\"'<>\s]+", downloads.text)
    if link is None:
        raise RuntimeError("không thấy link AllMeetings trong tab Downloads")
    resp = session.get(urljoin(page.url, html.unescape(link.group())), timeout=60)
    resp.raise_for_status()
    if "History for" not in resp.text[:500]:
        raise RuntimeError("CSV QuikStrike sai định dạng")
    return resp.text


def _meeting_groups(header: list[str], width: int) -> list[tuple[pd.Timestamp, int, int]]:
    starts = [(i, _MEETING_HEADER.search(c)) for i, c in enumerate(header)]
    starts = [(i, pd.to_datetime(m.group(1), format="%d %b %Y")) for i, m in starts if m]
    bounds = [i for i, _ in starts[1:]] + [width]
    return [(meeting, i, min(end, width)) for (i, meeting), end in zip(starts, bounds, strict=True)]


def parse_quikstrike_csv(text: str) -> pd.DataFrame:
    """CSV FedMeetingHistory (2 dòng tiêu đề: kỳ họp, khoảng bp) thành bảng dài, bỏ xác suất 0."""
    rows = list(csv.reader(io.StringIO(text)))
    header, labels, body = rows[0], rows[1], [r for r in rows[2:] if r and r[0]]
    width = len(labels)
    data = pd.DataFrame([r[:width] + [""] * (width - len(r)) for r in body])
    asof = pd.to_datetime(data[0], format="%m/%d/%Y")
    parts = []
    for meeting, first, last in _meeting_groups(header, width):
        if first >= last:
            continue  # kỳ họp chưa có cột dữ liệu
        block = data.iloc[:, first:last].replace("", None).apply(pd.to_numeric, errors="coerce")
        block.columns = [labels[i] for i in range(first, last)]
        block.insert(0, "asof", asof)
        long = block.melt(id_vars="asof", var_name="label", value_name="prob").dropna()
        long["meeting_date"] = meeting
        parts.append(long[long["prob"] > 0])
    out = pd.concat(parts, ignore_index=True)
    bounds = out["label"].str.extract(_RANGE).astype(int)
    out["range_low_bp"], out["range_high_bp"] = bounds[0], bounds[1]
    out["source"] = QS_SOURCE
    out = out[calc.LONG_COLUMNS].sort_values(["asof", "meeting_date", "range_low_bp"])
    return out.reset_index(drop=True)


def fetch_quikstrike(session: requests.Session | None = None) -> pd.DataFrame:
    return parse_quikstrike_csv(fetch_quikstrike_csv(session))


def parse_fomc_calendar(page: str) -> pd.DataFrame:
    """Ngày quyết định (ngày thứ 2 của kỳ họp). Bỏ notation vote / unscheduled."""
    panels = re.split(r"<h4><a[^>]*>(\d{4}) FOMC Meetings</a></h4>", page)
    rows = []
    for year, body in zip(panels[1::2], panels[2::2], strict=True):
        pairs = re.findall(
            r"fomc-meeting__month[^>]*><strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)<",
            body,
            re.S,
        )
        rows.extend(_meeting_row(int(year), month, days) for month, days in pairs)
    out = pd.DataFrame([r for r in rows if r is not None])
    return out.drop_duplicates("meeting_date").sort_values("meeting_date").reset_index(drop=True)


def _meeting_row(year: int, month: str, days: str) -> dict | None:
    if "(" in days:  # "(notation vote)", "(unscheduled)": không phải kỳ họp định kỳ
        return None
    last_day = int(re.findall(r"\d+", days)[-1])
    last_month = month.split("/")[-1].strip()
    date = pd.to_datetime(f"{last_day} {last_month[:3]} {year}", format="%d %b %Y")
    return {"meeting_date": date, "label": f"{month.strip()} {days.strip()} {year}"}


def fetch_fomc_calendar(session: requests.Session | None = None) -> pd.DataFrame:
    session = session or _session()
    resp = session.get(FOMC_URL, timeout=30)
    resp.raise_for_status()
    return parse_fomc_calendar(resp.text)


def zq_tickers_for(meetings: pd.Series, today: pd.Timestamp) -> list[str]:
    """Hợp đồng từ tháng hiện tại tới tháng sau kỳ họp cuối (hợp đồng đã hết hạn Yahoo không có)."""
    first = today.to_period("M")
    future = meetings[meetings > today]
    last = (future.max() if not future.empty else today).to_period("M") + 1
    return calc.zq_tickers_between(first, last)


def fetch_zq_prices(tickers: list[str], start: str, pause: float | None = None) -> pd.DataFrame:
    frames, _ = yahoo.fetch_yahoo(tickers, start, pause=pause)
    parts = [
        pd.DataFrame({"date": df["date"], "ticker": ticker, "close": df["close"]})
        for ticker, df in frames.items()
    ]
    if not parts:
        raise RuntimeError("Yahoo không trả giá ZQ nào")
    return pd.concat(parts, ignore_index=True)


def load_fred_inputs(start: str) -> pd.DataFrame:
    """DFEDTARU/L, EFFR, DFF: tải mới; thiếu thì lấy từ cache fred.xlsx."""
    frames, _ = fred.fetch_fred(FRED_INPUTS, start, fred.get_api_key())
    fresh = fred.frames_to_long(frames, pd.DataFrame(), fred.PREFIX, fred.SOURCE)
    cached = fred.load_fred_series()
    cached = cached[cached["series_id"].isin([fred.PREFIX + s for s in FRED_INPUTS])]
    missing = cached[~cached["series_id"].isin(set(fresh["series_id"]))]
    return pd.concat([fresh, missing], ignore_index=True)


def merge_history(new: pd.DataFrame, old: pd.DataFrame | None, keys: list[str]) -> pd.DataFrame:
    """Nối lịch sử: dòng cũ có cùng khóa (vd asof×kỳ họp) với dòng mới bị thay."""
    if old is None or old.empty:
        return new
    old = _parse_dates(old)
    new_keys = pd.MultiIndex.from_frame(new[keys].drop_duplicates())
    keep = ~pd.MultiIndex.from_frame(old[keys]).isin(new_keys)
    merged = pd.concat([old[keep], new], ignore_index=True)
    return merged.sort_values(keys).reset_index(drop=True)


def _parse_dates(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in _DATE_COLUMNS:
        if col in out.columns:
            out[col] = pd.to_datetime(out[col]).dt.normalize()
    return out


def _meta_row(name: str, df: pd.DataFrame | None, error: str = "") -> dict:
    ok = df is not None and not df.empty
    date_col = next((c for c in ("asof", "date", "meeting_date") if ok and c in df.columns), None)
    return {
        "series_id": f"fedwatch.{name}",
        "sheet": name,
        "fetched_at": excel_cache.utc_now_iso(),
        "n_obs": len(df) if ok else 0,
        "last_date": df[date_col].max().date().isoformat() if date_col else "",
        "status": "ok" if ok else "error",
        "error": "" if ok else error[:300],
    }


def _try(name: str, func, *args) -> tuple[pd.DataFrame | None, str]:
    try:
        return func(*args), ""
    except Exception as exc:  # 1 nguồn lỗi không dừng nguồn khác
        error = fred.sanitize(f"{type(exc).__name__}: {exc}")
        log.warning("FedWatch %s lỗi: %s", name, error)
        return None, error


def _computed(calendar: pd.DataFrame, today: pd.Timestamp, n_history_days: int) -> tuple:
    tickers = zq_tickers_for(calendar["meeting_date"], today)
    start = (today - pd.Timedelta(days=150)).date().isoformat()
    prices = fetch_zq_prices(tickers, start)
    fred_inputs = load_fred_inputs((today - pd.Timedelta(days=400)).date().isoformat())
    computed = calc.compute_fedwatch_history(
        prices, calendar["meeting_date"], fred_inputs, n_days=n_history_days
    )
    if computed.empty:
        raise RuntimeError("không tính được kỳ họp nào (thiếu giá ZQ hoặc biên lãi suất)")
    return prices, computed


def refresh_fedwatch_cache(
    cache_path: Path = DEFAULT_CACHE, n_history_days: int = 60
) -> pd.DataFrame:
    old, _ = excel_cache.read_cache(cache_path)
    today = pd.Timestamp.today().normalize()
    new: dict[str, pd.DataFrame | None] = {}
    errors: dict[str, str] = {}
    new["fomc_calendar"], errors["fomc_calendar"] = _try("fomc_calendar", fetch_fomc_calendar)
    new["quikstrike"], errors["quikstrike"] = _try("quikstrike", fetch_quikstrike)
    calendar = new["fomc_calendar"]
    if calendar is None:
        calendar = _parse_dates(old.get("fomc_calendar", pd.DataFrame(columns=["meeting_date"])))
    result, errors["computed"] = _try("computed", _computed, calendar, today, n_history_days)
    new["zq_prices"], new["computed"] = result if result is not None else (None, None)
    errors["zq_prices"] = errors["computed"]
    frames = _merge_all(new, old)
    meta = pd.DataFrame([_meta_row(n, new[n], errors.get(n, "")) for n in SHEETS])
    excel_cache.write_cache(cache_path, frames, meta)
    return meta


def _merge_all(new: dict, old: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    frames = {}
    for name in SHEETS:
        fresh, previous = new.get(name), old.get(name)
        if fresh is None:
            if previous is not None:
                frames[name] = previous
            continue
        keys = _HISTORY_KEYS.get(name)
        frames[name] = merge_history(fresh, previous, keys) if keys else fresh
    return frames


def load_fedwatch(cache_path: Path = DEFAULT_CACHE) -> dict[str, pd.DataFrame]:
    """{'quikstrike', 'computed', 'fomc_calendar', 'zq_prices', '_meta'}; sheet thiếu trả rỗng."""
    frames, meta = excel_cache.read_cache(cache_path)
    out = {name: _parse_dates(frames.get(name, pd.DataFrame())) for name in SHEETS}
    for name in ("quikstrike", "computed"):
        if out[name].empty:
            out[name] = pd.DataFrame(columns=calc.LONG_COLUMNS)
    out["_meta"] = meta
    return out
