"""AI comment: câu theo tab, chọn câu theo dấu điểm / hướng lệch, kỳ vọng lãi Fed (một thước đo)."""

import numpy as np
import pandas as pd

from macro_app import profiles as pf
from macro_app.config import load_catalog
from macro_app.metrics import forward as fw
from macro_app.metrics import implications as im

NOTES = {
    "tab": {"x": {"bad": "x xấu ở tab", "good": "x tốt ở tab"}},
    "chung": {"x": {"bad": "x xấu chung"}, "y": {"bad": "y xấu chung"}},
    "hai": {"c": {"bad_low": "thấp quá", "bad_high": "cao quá", "good": "vừa"}},
}
ASOF = pd.Timestamp("2026-10-08")


def _path(exp: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2026-10-28", periods=len(exp), freq="45D")
    return pd.DataFrame({"meeting_date": dates, "exp_upper": exp, "asof": ASOF, "source": "CME"})


def test_note_by_tab_then_common_then_override():
    assert im.note_of({"code": "x"}, -1.0, NOTES, "tab") == ("bad", "x xấu ở tab")
    assert im.note_of({"code": "x"}, 2.0, NOTES, "tab") == ("good", "x tốt ở tab")
    assert im.note_of({"code": "y"}, -1.0, NOTES, "tab") == ("bad", "y xấu chung")  # dự phòng
    assert im.note_of({"code": "x"}, 0.0, NOTES, "tab") == ("", "")  # trung tính: không hiện
    assert im.note_of({"code": "x"}, np.nan, NOTES, "tab") == ("", "")
    assert im.note_of({"code": "x", "note_bad": "riêng"}, -2, NOTES, "tab") == ("bad", "riêng")


def test_two_sided_row_picks_low_or_high_sentence():
    row = {"code": "c", "side": "both", "cuts": [8, 11, 16, 20]}
    assert im.note_of(row, -2, NOTES, "hai", measured=6.0)[1] == "thấp quá"
    assert im.note_of(row, -2, NOTES, "hai", measured=22.0)[1] == "cao quá"
    assert im.note_of(row, 2, NOTES, "hai", measured=13.0)[1] == "vừa"


def test_fed_outlook_single_measure():
    o = im.fed_outlook(_path([4.05, 4.24, 4.33, 4.50, 4.59, 4.69, 4.72, 4.76]), 4.0)
    assert o["end_date"] <= ASOF + pd.DateOffset(months=12)
    assert round(o["change_bps"]) == 76 and o["steps"] == 3  # 76 bps ≈ 3 bước 25 bps
    tone, text = im.fed_note(o)
    assert tone == "bad" and "tăng khoảng 3 lần" in text and "về 4,76%" in text
    cut = im.fed_note(im.fed_outlook(_path([3.9, 3.62]), 4.0))
    assert cut[0] == "good" and "giảm khoảng 2 lần" in cut[1]
    flat = im.fed_note(im.fed_outlook(_path([4.05]), 4.0))  # +5 bps: chưa đủ nửa bước
    assert flat[0] == "" and "giữ nguyên" in flat[1]
    assert im.fed_outlook(_path([]), 4.0) is None
    assert im.fed_outlook(_path([4.0]), np.nan) is None


def test_expected_change_history_uses_fed_rate_on_each_day():
    probs = pd.DataFrame(
        {
            "asof": ["2026-01-05"] * 2 + ["2026-06-01"] * 2,
            "meeting_date": pd.to_datetime(["2026-03-18", "2026-12-09"] * 2),
            "range_low_bp": [350, 375, 375, 400],
            "range_high_bp": [375, 400, 400, 425],
            "prob": [1.0, 1.0, 1.0, 1.0],
            "source": "CME",
        }
    )
    upper = pd.Series([3.75, 4.0], index=pd.to_datetime(["2025-12-10", "2026-04-29"]))
    s = fw.expected_change_history({"quikstrike": probs}, upper)
    assert s.round(1).tolist() == [25.0, 25.0]  # 4,00 − 3,75 rồi 4,25 − 4,00


def test_implications_order_and_single_fed_item():
    card = {"rows": [{"code": c} for c in ("a", "b", "c", "fedwatch_12m", "effr")]}
    table = pd.DataFrame(
        {
            "code": ["a", "b", "c", "fedwatch_12m", "effr"],
            "score": [-1.0, 2.0, -2.0, -1.0, np.nan],
            "contribution": [-0.1, 0.3, -0.4, -0.05, np.nan],
            "label": ["Xấu", "Rất tốt", "Rất xấu", "Xấu", ""],
            "info": [False, False, False, False, True],
        }
    )
    notes = {"t": {c: {"bad": f"{c}-", "good": f"{c}+"} for c in "abc"}}
    fed = im.fed_outlook(_path([4.25]), 4.0)
    items = im.implications(card, table, {}, notes, seg="t", fed=fed, limit=3)
    assert [x["code"] for x in items] == ["c", "a", "fedwatch_12m"]  # Fed luôn giữ, chỉ 1 mục
    assert [x["code"] for x in im.implications(card, table, {}, notes, seg="t")] == ["c", "a", "b"]


def test_notes_survive_save_and_rule_edit():
    row = {"code": "x", "pillar": "P", "method": "absolute", "cuts": [1, 2], "note_bad": "n"}
    assert pf.clean_row(row)["note_bad"] == "n"
    card = pf.set_row_cfg({"rows": [row]}, "x", {"method": "absolute", "cuts": [0, 3]})
    assert card["rows"][0]["note_bad"] == "n"
    card = pf.set_row_notes(card, "x", "  ", "tốt")
    assert "note_bad" not in card["rows"][0] and card["rows"][0]["note_good"] == "tốt"


def test_every_scored_row_has_notes_for_its_tab():
    """Mỗi dòng tính điểm trong các bộ có sẵn có câu cho đúng tab (hai chiều: thấp và cao)."""
    notes, cat = im.load_notes(), {i.code for i in load_catalog()}
    missing = []
    for slug, prof in pf.load_profiles().items():
        for seg, card in prof["segments"].items():
            for r in card["rows"]:
                if r.get("info") or r["code"] in im.FED_CODES:
                    continue
                n = im.default_note(notes, seg, r["code"])
                need = (
                    ("bad_low", "bad_high", "good") if r.get("side") == "both" else ("bad", "good")
                )
                if not all(n.get(k) for k in need):
                    missing.append((slug, seg, r["code"]))
    assert missing == []
    assert {c for tab in notes.values() for c in tab} <= cat
