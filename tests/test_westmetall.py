import pandas as pd
import pytest

from macro_app.io import westmetall

HTML = """
<table><tr><th class="text">date</th><th>LME Copper Cash-Settlement</th>
<th>LME Copper 3-month</th>
<th class="text last">LME Copper stock</th></tr>
<tr><td >05. October 2026</td>
<td >14,430.00</td>
<td >14,366.00</td>
<td class="last">244,900</td></tr>
<tr><td >02. October 2026</td><td >14,355.00</td><td >14,320.00</td>
<td class="last">248,650</td></tr>
<tr><td >01. October 2026</td><td >-</td><td >14,290.00</td><td class="last">248,075</td></tr>
</table>"""


def test_parse_table():
    df = westmetall.parse_table(HTML)
    assert df["date"].tolist() == list(pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-05"]))
    assert df["lme.copper_cash"].iloc[-1] == pytest.approx(14430.0)
    assert df["lme.copper_stock"].iloc[-1] == 244900
    assert pd.isna(df["lme.copper_cash"].iloc[0])  # "-" → NaN


def test_refresh_merges_and_loads(tmp_path, monkeypatch):
    monkeypatch.setattr(
        westmetall, "fetch_years", lambda years, session, sleep: westmetall.parse_table(HTML)
    )
    path = tmp_path / "lme.xlsx"
    meta = westmetall.refresh_lme_cache(path, sleep=0)
    assert (meta["status"] == "ok").all()
    store = westmetall.load_lme_series(path)
    cash = store[store["series_id"] == "lme.copper_cash"]
    assert len(cash) == 2 and set(store["source"]) == {"LME (Westmetall)"}
