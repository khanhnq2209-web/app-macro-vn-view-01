import pandas as pd
import pytest

from macro_app.io import excel_cache, fred

FAKE_KEY = "abcdef0123456789abcdef0123456789"  # pragma: allowlist secret (key giả cho test)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession:
    """series DFF ok (daily), CPIAUCSL ok (monthly), BAD → HTTP 400, BOOM → exception có URL+key."""

    def __init__(self):
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        sid = params["series_id"]
        if sid == "BAD":
            return FakeResponse(400, {"error_message": "Bad Request. Invalid series_id."})
        if sid == "BOOM":
            raise ConnectionError(f"failed: {url}?series_id=BOOM&api_key={params['api_key']}")
        if url.endswith("/series"):
            freq = "M" if sid == "CPIAUCSL" else "D"
            return FakeResponse(
                200, {"seriess": [{"title": sid, "units": "u", "frequency_short": freq}]}
            )
        obs = {
            "DFF": [
                {"date": "2026-10-01", "value": "4.10"},
                {"date": "2026-10-02", "value": "."},
                {"date": "2026-10-03", "value": "4.12"},
            ],
            "CPIAUCSL": [
                {"date": "2026-07-01", "value": "320.1"},
                {"date": "2026-08-01", "value": "321.0"},
            ],
        }[sid]
        return FakeResponse(200, {"observations": obs})


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(fred, "REQUEST_SLEEP_SECONDS", 0)


def test_observations_dot_is_missing_and_monthly_to_month_end():
    obs = [{"date": "2026-07-01", "value": "1.5"}, {"date": "2026-08-01", "value": "."}]
    monthly = fred.observations_to_frame(obs, "M")
    assert monthly["date"].tolist() == [pd.Timestamp("2026-07-31")]
    assert monthly["value"].tolist() == [1.5]
    weekly = fred.observations_to_frame(obs, "W")
    assert weekly["date"].tolist() == [pd.Timestamp("2026-07-01")]


def test_fetch_fred_one_failure_does_not_stop_and_key_never_leaks():
    frames, meta = fred.fetch_fred(
        ["DFF", "BAD", "BOOM", "CPIAUCSL"], "2026-01-01", FAKE_KEY, session=FakeSession()
    )
    assert set(frames) == {"DFF", "CPIAUCSL"}
    assert frames["DFF"]["value"].tolist() == [4.10, 4.12]
    assert frames["CPIAUCSL"]["date"].max() == pd.Timestamp("2026-08-31")
    status = dict(zip(meta["series_id"], meta["status"], strict=True))
    assert status == {
        "fred.DFF": "ok",
        "fred.BAD": "error",
        "fred.BOOM": "error",
        "fred.CPIAUCSL": "ok",
    }
    assert not meta.astype(str).apply(lambda col: col.str.contains(FAKE_KEY)).any().any()
    assert "api_key=***" in meta.set_index("series_id").loc["fred.BOOM", "error"]


def test_sanitize_strips_key_in_url_and_raw():
    msg = f"GET https://x/fred?series_id=A&api_key={FAKE_KEY}&file_type=json; key {FAKE_KEY}"
    clean = fred.sanitize(msg, FAKE_KEY)
    assert FAKE_KEY not in clean


def test_refresh_keeps_previous_sheet_for_failed_series(tmp_path, monkeypatch):
    path = tmp_path / "fred.xlsx"
    monkeypatch.setattr(fred, "get_api_key", lambda: FAKE_KEY)
    monkeypatch.setattr(fred.requests, "Session", FakeSession)
    meta1 = fred.refresh_fred_cache(path, ids=["DFF", "CPIAUCSL"], start="2026-01-01")
    assert (meta1["status"] == "ok").all()

    class CpiDown(FakeSession):
        def get(self, url, params=None, timeout=None):
            if params["series_id"] == "CPIAUCSL":
                return FakeResponse(500, {"error_message": "Internal Server Error"})
            return super().get(url, params, timeout)

    monkeypatch.setattr(fred.requests, "Session", CpiDown)
    fred.refresh_fred_cache(path, ids=["DFF", "CPIAUCSL"], start="2026-01-01")
    frames, meta = excel_cache.read_cache(path)
    assert "CPIAUCSL" in frames  # sheet cũ được giữ
    row = meta.set_index("series_id").loc["fred.CPIAUCSL"]
    assert row["status"] == "error"
    assert row["n_obs"] == 2

    store = fred.load_fred_series(path)
    assert list(store.columns) == ["series_id", "date", "value", "source"]
    assert set(store["series_id"]) == {"fred.DFF", "fred.CPIAUCSL"}
    assert store["date"].dtype == "datetime64[ns]"
    assert store["value"].dtype == float
    assert (store["source"] == "FRED").all()


def test_load_missing_cache_returns_empty_contract(tmp_path):
    store = fred.load_fred_series(tmp_path / "none.xlsx")
    assert store.empty
    assert list(store.columns) == ["series_id", "date", "value", "source"]


@pytest.mark.live
def test_live_fred_dff():
    key = fred.get_api_key()
    if not key:
        pytest.skip("FRED_API_KEY chưa đặt")
    frames, meta = fred.fetch_fred(["DFF"], "2026-01-01", key)
    assert meta["status"].iloc[0] == "ok"
    assert len(frames["DFF"]) > 100
