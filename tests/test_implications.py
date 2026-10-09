"""Hàm ý theo mức và triển vọng lãi Fed (đếm số lần dự báo tăng / giảm 12 tháng tới)."""

import numpy as np
import pandas as pd

from macro_app import profiles as pf
from macro_app.config import load_catalog
from macro_app.metrics import implications as im

DEFAULTS = {"x": {"bad": "x xấu", "good": "x tốt"}}
ASOF = pd.Timestamp("2026-10-08")


def _path(tops: list[float], exp: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2026-10-28", periods=len(tops), freq="45D")
    return pd.DataFrame(
        {"meeting_date": dates, "top_upper": tops, "exp_upper": exp, "asof": ASOF, "source": "CME"}
    )


def test_note_by_score_sign_and_override():
    assert im.note_of({"code": "x"}, -1.0, DEFAULTS) == ("bad", "x xấu")
    assert im.note_of({"code": "x"}, 2.0, DEFAULTS) == ("good", "x tốt")
    assert im.note_of({"code": "x"}, 0.0, DEFAULTS) == ("", "")  # trung tính: không note
    assert im.note_of({"code": "x"}, np.nan, DEFAULTS) == ("", "")
    assert im.note_of({"code": "x", "note_bad": "riêng"}, -2, DEFAULTS) == ("bad", "riêng")
    assert im.note_of({"code": "y"}, -2, DEFAULTS) == ("", "")  # không có câu


def test_fed_outlook_counts_hikes_from_current():
    # hiện tại 4,00: 4,00 (giữ) → 4,25 (tăng) → 4,25 → 4,50 (tăng) → 4,25 (giảm)
    o = im.fed_outlook(_path([4.0, 4.25, 4.25, 4.5, 4.25], [4.05, 4.2, 4.3, 4.45, 4.4]), 4.0)
    assert len(o["hikes"]) == 2 and len(o["cuts"]) == 1
    assert round(o["change_bps"]) == 40
    tone, text = im.fed_note(o)
    assert tone == "bad" and "tăng 2 lần" in text and "giảm 1 lần" in text


def test_fed_outlook_only_next_12_months_and_cuts_are_good():
    path = _path([3.75, 3.5] + [3.5] * 10, [3.8, 3.55] + [3.5] * 10)
    o = im.fed_outlook(path, 4.0)
    assert o["end_date"] <= ASOF + pd.DateOffset(months=12)
    assert len(o["cuts"]) == 2 and not o["hikes"]
    assert im.fed_note(o)[0] == "good"
    assert im.fed_outlook(path.iloc[0:0], 4.0) is None
    assert im.fed_outlook(path, np.nan) is None


def test_implications_order_and_single_fed_item():
    card = {"rows": [{"code": c} for c in ("a", "b", "c", "fed_upper", "effr")]}
    table = pd.DataFrame(
        {
            "code": ["a", "b", "c", "fed_upper", "effr"],
            "score": [-1.0, 2.0, -2.0, 1.0, np.nan],
            "contribution": [-0.1, 0.3, -0.4, 0.1, np.nan],
            "label": ["Xấu", "Rất tốt", "Rất xấu", "Tốt", ""],
            "info": [False, False, False, False, True],
        }
    )
    notes = {c: {"bad": f"{c}-", "good": f"{c}+"} for c in "abc"}
    fed = im.fed_outlook(_path([4.25], [4.25]), 4.0)
    items = im.implications(card, table, {}, notes, fed=fed, limit=3)
    assert [x["code"] for x in items] == ["c", "a", "fed_upper"]  # Fed luôn giữ, chỉ 1 mục
    assert [x["code"] for x in im.implications(card, table, {}, notes)] == ["c", "a", "b"]


def test_notes_survive_save_and_rule_edit():
    row = {"code": "x", "pillar": "P", "method": "absolute", "cuts": [1, 2], "note_bad": "n"}
    assert pf.clean_row(row)["note_bad"] == "n"
    card = pf.set_row_cfg({"rows": [row]}, "x", {"method": "absolute", "cuts": [0, 3]})
    assert card["rows"][0]["note_bad"] == "n"
    card = pf.set_row_notes(card, "x", "  ", "tốt")
    assert "note_bad" not in card["rows"][0] and card["rows"][0]["note_good"] == "tốt"


def test_every_scored_row_has_default_notes():
    """Mỗi chỉ số tính điểm trong các bộ có sẵn đều có câu hàm ý bất lợi và thuận lợi."""
    notes, cat = im.load_notes(), {i.code for i in load_catalog()}
    missing = [
        (slug, r["code"])
        for slug, prof in pf.load_profiles().items()
        for card in prof["segments"].values()
        for r in card["rows"]
        if not r.get("info")
        and r["code"] not in im.FED_CODES
        and not (notes.get(r["code"], {}).get("bad") and notes[r["code"]].get("good"))
    ]
    assert missing == []
    assert set(notes) <= cat
