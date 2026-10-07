from pathlib import Path

import pandas as pd
import pytest

from macro_app.io import excel_cache, fedwatch
from macro_app.metrics import fedwatch_calc as calc

FIXTURE = Path(__file__).parent / "fixtures" / "quikstrike_allmeetings_sample.csv"
P = pd.Period
T = pd.Timestamp


def probs(df: pd.DataFrame, meeting: str) -> dict[int, float]:
    sub = df[df["meeting_date"] == T(meeting)]
    return {int(k): round(v, 6) for k, v in zip(sub["range_low_bp"], sub["prob"], strict=True)}


def price(rate: float) -> float:
    return 100.0 - rate


# ---------------- phương pháp tự tính ----------------
@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (0.0, {0: 1.0}),
        (-0.125, {0: 0.5, -1: 0.5}),
        (0.0625, {0: 0.75, 1: 0.25}),
        (-0.25, {-1: 1.0}),
        (-0.375, {-1: 0.5, -2: 0.5}),
    ],
)
def test_move_distribution(delta, expected):
    got = calc.move_distribution(delta)
    assert got.keys() == expected.keys()
    for key, value in expected.items():
        assert got[key] == pytest.approx(value)


def test_golden_mid_month_meeting_half_cut():
    """Họp 15/11 (30 ngày), tháng 10 không họp: r_start=3.875; ngụ ý 50% giảm 25bp."""
    nov_avg = 0.5 * 3.875 + 0.5 * 3.75
    prices = {P("2026-10"): price(3.875), P("2026-11"): price(nov_avg)}
    out = calc.compute_fedwatch(prices, [T("2026-11-15")], 375, 3.875, T("2026-10-05"))
    assert probs(out, "2026-11-15") == {350: 0.5, 375: 0.5}
    assert (out["range_high_bp"] - out["range_low_bp"] == 25).all()
    assert (out["source"] == calc.SOURCE_COMPUTED).all()


def test_golden_late_month_meeting_uses_next_month_contract():
    """Họp 28/10 (7 ngày cuối tháng) → r_end = r tháng 11 (không họp) = 3.80 ⇒ 30% giảm."""
    prices = {P("2026-10"): price(3.87), P("2026-11"): price(3.80)}
    out = calc.compute_fedwatch(prices, [T("2026-10-28")], 375, 3.875, T("2026-10-05"))
    assert probs(out, "2026-10-28") == {350: 0.3, 375: 0.7}


def test_golden_two_chained_meetings():
    """28/10: 30% giảm; 9/12 (r_start = r tháng 11): Δ = −0.375 ⇒ 1 hoặc 2 bước, 50/50."""
    dec_start, dec_end = 3.80, 3.80 - 0.375
    dec_avg = 9 / 31 * dec_start + 22 / 31 * dec_end
    prices = {P("2026-10"): price(3.87), P("2026-11"): price(3.80), P("2026-12"): price(dec_avg)}
    meetings = [T("2026-10-28"), T("2026-12-09")]
    out = calc.compute_fedwatch(prices, meetings, 375, 3.875, T("2026-10-05"))
    assert probs(out, "2026-10-28") == {350: 0.3, 375: 0.7}
    # {0: .7, −1: .3} ⊗ {−1: .5, −2: .5} = {−1: .35, −2: .5, −3: .15}
    assert probs(out, "2026-12-09") == {300: 0.15, 325: 0.5, 350: 0.35}


def test_consecutive_meeting_months_chain_end_to_start():
    """Tháng 12 và 1 đều có họp: r_start(1) = r_end(12)."""
    dec_end = 3.625
    dec_avg = 9 / 31 * 3.875 + 22 / 31 * dec_end
    jan_end = dec_end - 0.25
    prices = {
        P("2026-11"): price(3.875),
        P("2026-12"): price(dec_avg),
        P("2027-01"): price(14 / 31 * dec_end + 17 / 31 * jan_end),
    }
    meetings = [T("2026-12-09"), T("2027-01-14")]
    out = calc.compute_fedwatch(prices, meetings, 375, 3.875, T("2026-11-02"))
    assert probs(out, "2026-12-09") == {350: 1.0}
    assert probs(out, "2027-01-14") == {325: 1.0}


def test_missing_contract_stops_chain():
    prices = {P("2026-10"): price(3.87), P("2026-11"): price(3.80)}
    meetings = [T("2026-10-28"), T("2027-03-17")]
    out = calc.compute_fedwatch(prices, meetings, 375, 3.875, T("2026-10-05"))
    assert set(out["meeting_date"]) == {T("2026-10-28")}


def test_zq_tickers():
    assert calc.zq_ticker(P("2026-10")) == "ZQV26.CBT"
    assert calc.zq_period("ZQF27.CBT") == P("2027-01")
    assert calc.zq_tickers_between(P("2026-11"), P("2027-01")) == [
        "ZQX26.CBT",
        "ZQZ26.CBT",
        "ZQF27.CBT",
    ]


def _fred_store(dates, lower, upper, effr):
    parts = [
        pd.DataFrame({"series_id": sid, "date": dates, "value": vals})
        for sid, vals in (("fred.DFEDTARL", lower), ("fred.DFEDTARU", upper), ("fred.EFFR", effr))
    ]
    return pd.concat(parts, ignore_index=True)


def test_history_uses_range_and_spread_at_each_asof():
    dates = pd.to_datetime(["2026-10-01", "2026-10-02"])
    # Ngày 2/10 biên đổi lên 400–425; EFFR = điểm giữa − 0.005
    fred_store = _fred_store(dates, [3.75, 4.00], [4.00, 4.25], [3.87, 4.12])
    rows = []
    for day, oct_p, nov_p in ((dates[0], 96.13, 96.20), (dates[1], 95.88, 95.88)):
        rows += [
            {"date": day, "ticker": "ZQV26.CBT", "close": oct_p},
            {"date": day, "ticker": "ZQX26.CBT", "close": nov_p},
        ]
    out = calc.compute_fedwatch_history(pd.DataFrame(rows), [T("2026-10-28")], fred_store)
    first = out[out["asof"] == dates[0]]
    second = out[out["asof"] == dates[1]]
    # 1/10: r_start = 3.87, r_end = 3.80 → Δ = −0.07 → 28% giảm
    assert probs(first, "2026-10-28") == {350: 0.28, 375: 0.72}
    # 2/10: r_start = 4.12, r_end = 4.12 → giữ nguyên ở khoảng mới
    assert probs(second, "2026-10-28") == {400: 1.0}


# ---------------- QuikStrike / lịch FOMC ----------------
def test_parse_quikstrike_fixture():
    out = fedwatch.parse_quikstrike_csv(FIXTURE.read_text(encoding="utf-8"))
    assert list(out.columns) == calc.LONG_COLUMNS
    assert out["asof"].max() == T("2026-10-02")
    assert out["meeting_date"].nunique() == 9  # kỳ 8/12/2027 chưa có cột dữ liệu
    sums = out.groupby(["asof", "meeting_date"])["prob"].sum()
    assert sums.between(0.999, 1.001).all()
    assert (out["range_high_bp"] - out["range_low_bp"] == 25).all()
    latest = out[out["asof"] == T("2026-10-02")]
    assert probs(latest, "2026-10-28") == {375: 0.778571, 400: 0.221429}
    assert (out["source"] == "CME QuikStrike").all()


FOMC_HTML = """
<h4><a id="1">2027 FOMC Meetings</a></h4>
<div class="fomc-meeting__month col"><strong>January</strong></div>
<div class="fomc-meeting__date col">26-27</div>
<h4><a id="2">2025 FOMC Meetings</a></h4>
<div class="fomc-meeting__month col"><strong>July</strong></div>
<div class="fomc-meeting__date col">29-30</div>
<div class="fomc-meeting__month col"><strong>August</strong></div>
<div class="fomc-meeting__date col">22 (notation vote)</div>
<div class="fomc-meeting__month col"><strong>Oct/Nov</strong></div>
<div class="fomc-meeting__date col">31-1</div>
<div class="fomc-meeting__month col"><strong>December</strong></div>
<div class="fomc-meeting__date col">9-10*</div>
"""


def test_parse_fomc_calendar_second_day_and_skip_notation_vote():
    out = fedwatch.parse_fomc_calendar(FOMC_HTML)
    assert out["meeting_date"].tolist() == [
        T("2025-07-30"),
        T("2025-11-01"),
        T("2025-12-10"),
        T("2027-01-27"),
    ]


class _Resp:
    def __init__(self, text, url="https://qs/User/QuikStrikeView.aspx?viewitemid=X"):
        self.text, self.url, self.status_code = text, url, 200

    def raise_for_status(self):
        return None


class FakeQsSession:
    def __init__(self, csv_text):
        self.csv_text, self.posted = csv_text, None

    def get(self, url, timeout=None):
        if "AllMeetings" in url:
            assert url == "https://qs/User/Export/FedWatch/AllMeetings.aspx?insid=1&qsid=a"
            return _Resp(self.csv_text, url)
        return _Resp(
            '<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="abc&amp;d" />'
            '<input type="hidden" name="__EVENTVALIDATION" value="ev" />'
        )

    def post(self, url, data=None, timeout=None):
        self.posted = data
        return _Resp('<a href="Export/FedWatch/AllMeetings.aspx?insid=1&amp;qsid=a">All</a>')


def test_fetch_quikstrike_csv_posts_downloads_tab():
    session = FakeQsSession(FIXTURE.read_text(encoding="utf-8"))
    text = fedwatch.fetch_quikstrike_csv(session)
    assert text.startswith(",History for")
    assert session.posted["__EVENTTARGET"] == fedwatch.QS_DOWNLOADS_TARGET
    assert session.posted["__VIEWSTATE"] == "abc&d"
    assert session.posted["__EVENTVALIDATION"] == "ev"


# ---------------- refresh ----------------
def test_merge_history_replaces_same_keys():
    old = pd.DataFrame({"asof": ["2026-10-01", "2026-10-02"], "meeting_date": ["2026-10-28"] * 2})
    old["prob"] = [0.1, 0.2]
    new = pd.DataFrame(
        {"asof": [T("2026-10-02")], "meeting_date": [T("2026-10-28")], "prob": [0.9]}
    )
    out = fedwatch.merge_history(new, old, ["asof", "meeting_date"])
    assert out["prob"].tolist() == [0.1, 0.9]


def test_refresh_one_source_failing_keeps_other_and_old(tmp_path, monkeypatch):
    path = tmp_path / "fedwatch.xlsx"
    qs = fedwatch.parse_quikstrike_csv(FIXTURE.read_text(encoding="utf-8"))
    calendar = pd.DataFrame({"meeting_date": [T("2026-10-28"), T("2026-12-09")]})
    computed = qs[qs["asof"] == T("2026-10-02")].assign(source=calc.SOURCE_COMPUTED)
    prices = pd.DataFrame({"date": [T("2026-10-02")], "ticker": ["ZQV26.CBT"], "close": [96.12]})
    monkeypatch.setattr(fedwatch, "fetch_quikstrike", lambda: qs)
    monkeypatch.setattr(fedwatch, "fetch_fomc_calendar", lambda: calendar)
    monkeypatch.setattr(fedwatch, "_computed", lambda *a: (prices, computed))
    meta = fedwatch.refresh_fedwatch_cache(path)
    assert (meta["status"] == "ok").all()

    def boom():
        raise ConnectionError("blocked")

    monkeypatch.setattr(fedwatch, "fetch_quikstrike", boom)
    meta = fedwatch.refresh_fedwatch_cache(path)
    status = dict(zip(meta["sheet"], meta["status"], strict=True))
    assert status["quikstrike"] == "error"
    assert status["computed"] == "ok"
    loaded = fedwatch.load_fedwatch(path)
    assert set(loaded) == {"quikstrike", "computed", "fomc_calendar", "zq_prices", "_meta"}
    assert len(loaded["quikstrike"]) == len(qs)  # bản cũ được giữ
    assert loaded["computed"]["asof"].dtype == "datetime64[ns]"
    _, meta_disk = excel_cache.read_cache(path)
    assert set(meta_disk["sheet"]) == set(fedwatch.SHEETS)


@pytest.mark.live
def test_live_quikstrike():
    out = fedwatch.fetch_quikstrike()
    assert out["meeting_date"].nunique() >= 5
    assert out.groupby(["asof", "meeting_date"])["prob"].sum().between(0.99, 1.01).all()


@pytest.mark.live
def test_live_fomc_calendar():
    out = fedwatch.fetch_fomc_calendar()
    assert (out["meeting_date"] > pd.Timestamp.today()).sum() >= 4
