import pandas as pd
import pytest

from macro_app.io import excel_cache, yahoo


def fake_history(closes: list[float], start: str = "2026-09-28") -> pd.DataFrame:
    index = pd.date_range(start, periods=len(closes), freq="D", tz="America/New_York")
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Adj Close": closes,
            "Volume": [100] * len(closes),
        },
        index=index,
    )


def fake_download(ticker: str, start: str) -> pd.DataFrame:
    if ticker == "BOOM":
        raise RuntimeError("HTTP 429 Too Many Requests")
    if ticker == "EMPTY":
        return pd.DataFrame()
    return fake_history([100.0, 101.5, 102.0])


def test_history_to_frame_tz_naive_and_value_is_close():
    frame = yahoo.history_to_frame(fake_history([1.0, 2.0]))
    assert list(frame.columns) == [
        "date",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "value",
    ]
    assert frame["date"].dt.tz is None
    assert frame["date"].iloc[0] == pd.Timestamp("2026-09-28")
    assert frame["value"].tolist() == [1.0, 2.0]


def test_fetch_yahoo_one_failure_does_not_stop(monkeypatch):
    monkeypatch.setattr(yahoo, "_download", fake_download)
    frames, meta = yahoo.fetch_yahoo(["DX-Y.NYB", "BOOM", "EMPTY", "BZ=F"], "2026-01-01", pause=0)
    assert set(frames) == {"DX-Y.NYB", "BZ=F"}
    status = dict(zip(meta["series_id"], meta["status"], strict=True))
    assert status["yahoo.BOOM"] == "error"
    assert status["yahoo.EMPTY"] == "error"
    assert status["yahoo.BZ=F"] == "ok"


def test_refresh_and_load_keep_previous(tmp_path, monkeypatch):
    path = tmp_path / "yahoo.xlsx"
    monkeypatch.setattr(yahoo, "_download", fake_download)
    monkeypatch.setattr(yahoo, "sleep_seconds", lambda: 0)
    yahoo.refresh_yahoo_cache(path, tickers=["DX-Y.NYB", "^VIX"], start="2026-01-01")

    def failing(ticker, start):
        if ticker == "^VIX":
            raise RuntimeError("down")
        return fake_download(ticker, start)

    monkeypatch.setattr(yahoo, "_download", failing)
    meta = yahoo.refresh_yahoo_cache(path, tickers=["DX-Y.NYB", "^VIX"], start="2026-01-01")
    assert meta.set_index("series_id").loc["yahoo.^VIX", "status"] == "error"
    frames, _ = excel_cache.read_cache(path)
    assert "^VIX" in frames

    store = yahoo.load_yahoo_series(path)
    assert set(store["series_id"]) == {"yahoo.DX-Y.NYB", "yahoo.^VIX"}
    assert (store["source"] == "Yahoo").all()
    assert store["date"].dtype == "datetime64[ns]"
    assert store.loc[store["series_id"] == "yahoo.^VIX", "value"].tolist() == [100.0, 101.5, 102.0]


@pytest.mark.live
def test_live_yahoo_dxy():
    frames, meta = yahoo.fetch_yahoo(["DX-Y.NYB"], "2026-01-01", pause=0)
    assert meta["status"].iloc[0] == "ok"
    assert frames["DX-Y.NYB"]["value"].between(50, 200).all()
