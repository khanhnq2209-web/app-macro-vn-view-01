"""API dulieukinhte (mock, không gọi mạng): đổi kỳ, phân trang, đè số cùng kỳ, lỗi không lộ key."""

import pandas as pd
import pytest

from macro_app.io import dulieukinhte_api as dl


def test_period_end_matches_raw_calendar():
    assert dl.period_end("2026-08") == pd.Timestamp("2026-08-31")
    assert dl.period_end("2026-Q2") == pd.Timestamp("2026-06-30")
    assert dl.period_end("2026") == pd.Timestamp("2026-12-31")


class FakeResp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, pages):
        self.pages, self.calls = list(pages), []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        return self.pages.pop(0)


def test_fetch_series_follows_cursor(monkeypatch):
    monkeypatch.setattr(dl, "PAUSE_SECONDS", 0)
    pages = [
        FakeResp(
            200,
            {
                "data": {"observations": [{"period": "2026-07", "value": 8.97}]},
                "meta": {"hasMore": True, "nextCursor": "abc"},
            },
        ),
        FakeResp(
            200,
            {
                "data": {
                    "observations": [
                        {"period": "2026-08", "value": 10.19},
                        {"period": "2026-09", "value": None},
                    ]
                },
                "meta": {"hasMore": False, "nextCursor": None},
            },
        ),
    ]
    s = FakeSession(pages)
    df = dl.fetch_series(s, 123, "2021-01-01")
    assert df["value"].tolist() == [8.97, 10.19]
    assert df["date"].iloc[-1] == pd.Timestamp("2026-08-31")
    assert s.calls[1][1]["cursor"] == "abc"


def test_error_message_has_no_key():
    s = FakeSession(
        [FakeResp(401, {"error": {"code": "invalid_key", "message": "Khoá không hợp lệ"}})]
    )
    with pytest.raises(RuntimeError) as exc:
        dl._get(s, "/series/1/observations")
    assert "invalid_key" in str(exc.value) and "Bearer" not in str(exc.value)


def test_overlay_new_vintage_wins_and_extends():
    store = pd.DataFrame(
        {
            "series_id": ["vn.credit_ytd"] * 2 + ["vn.other"],
            "date": pd.to_datetime(["2026-04-30", "2026-05-31", "2026-05-31"]),
            "value": [4.59, 4.72, 1.0],
            "source": "dulieukinhte",
        }
    )
    api = pd.DataFrame(
        {
            "series_id": ["vn.credit_ytd"] * 2,
            "date": pd.to_datetime(["2026-05-31", "2026-08-31"]),
            "value": [5.96, 10.19],
            "source": dl.SOURCE,
        }
    )
    out = dl.overlay(store, api).set_index(["series_id", "date"])["value"]
    assert (
        out[("vn.credit_ytd", pd.Timestamp("2026-05-31"))] == 5.96
    )  # nguồn sửa lùi → bản mới thắng
    assert out[("vn.credit_ytd", pd.Timestamp("2026-04-30"))] == 4.59  # kỳ API không có → giữ Excel
    assert out[("vn.credit_ytd", pd.Timestamp("2026-08-31"))] == 10.19
    assert out[("vn.other", pd.Timestamp("2026-05-31"))] == 1.0


def test_refresh_without_key_raises_clear_message(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "get_api_key", lambda: "")
    with pytest.raises(RuntimeError, match="DLKT_API_KEY"):
        dl.refresh_cache(cache=tmp_path / "c.csv", meta_file=tmp_path / "m.json")


def test_refresh_skips_within_min_days_without_calling_api(tmp_path, monkeypatch):
    import json
    from datetime import UTC, datetime

    cache, meta = tmp_path / "c.csv", tmp_path / "m.json"
    cache.write_text("series_id,date,value,source\n", encoding="utf-8")
    meta.write_text(json.dumps({"fetched_at": datetime.now(UTC).isoformat()}), encoding="utf-8")
    monkeypatch.setattr(
        dl, "get_api_key", lambda: (_ for _ in ()).throw(AssertionError("không được gọi API"))
    )
    out = dl.refresh_cache(cache=cache, meta_file=meta)
    assert out["skipped"] is True


def test_refresh_force_ignores_min_days(tmp_path, monkeypatch):
    import json
    from datetime import UTC, datetime

    cache, meta = tmp_path / "c.csv", tmp_path / "m.json"
    cache.write_text("series_id,date,value,source\n", encoding="utf-8")
    meta.write_text(json.dumps({"fetched_at": datetime.now(UTC).isoformat()}), encoding="utf-8")
    monkeypatch.setattr(dl, "get_api_key", lambda: "")
    with pytest.raises(RuntimeError, match="DLKT_API_KEY"):
        dl.refresh_cache(cache=cache, meta_file=meta, force=True)
