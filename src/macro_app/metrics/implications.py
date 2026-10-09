"""AI comment: hàm ý của từng chỉ số cho Việt Nam, và kỳ vọng lãi Fed 12 tháng tới (FedWatch).

Câu viết sẵn ở config/implications.yaml theo TỪNG TAB (cùng một mã có nghĩa khác nhau ở bộ
Tỷ giá và bộ Nhà ở), mục `chung` làm dự phòng; dòng trong bộ ghi đè bằng note_bad / note_good.
Lãi Fed: một thước đo duy nhất là biên trên kỳ vọng (bình quân xác suất) ở kỳ họp cuối trong 12
tháng tới trừ biên trên hiện tại; số lần = làm tròn(chênh / 25 bps).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from macro_app import fmt
from macro_app.paths import CONFIG_DIR

FED_CODES = ("fedwatch_12m", "fed_upper", "fed_lower", "effr")
FED_STEP_BPS = 25.0  # một bước điều chỉnh thông thường của Fed
COMMON = "chung"


def load_notes(config_dir: Path = CONFIG_DIR) -> dict[str, dict]:
    """{tab: {mã: {bad, good}}}; tab `chung` dùng khi tab không có câu cho mã đó."""
    path = config_dir / "implications.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def default_note(defaults: dict, seg: str, code: str) -> dict:
    return (defaults.get(seg) or {}).get(code) or (defaults.get(COMMON) or {}).get(code) or {}


def note_of(
    row: dict, score: float, defaults: dict, seg: str, measured: float = np.nan
) -> tuple[str, str]:
    """(bad|good, câu) theo dấu điểm của dòng; trung tính hoặc chưa có số thì ("", "").

    Dòng chấm hai chiều (side both): bất lợi có hai nguyên nhân ngược nhau nên dùng câu
    `bad_low` / `bad_high` theo số đo nằm dưới hay trên vùng giữa của các mốc.
    """
    if score is None or pd.isna(score) or score == 0:
        return "", ""
    tone = "bad" if score < 0 else "good"
    note = default_note(defaults, seg, row["code"])
    text = row.get(f"note_{tone}") or note.get(tone, "")
    cuts = sorted(row.get("cuts") or [])
    if tone == "bad" and row.get("side") == "both" and cuts and not pd.isna(measured):
        center = (cuts[len(cuts) // 2 - 1] + cuts[len(cuts) // 2]) / 2
        text = row.get("note_bad") or note.get("bad_low" if measured < center else "bad_high", text)
    return (tone, text) if text else ("", "")


def fed_outlook(path: pd.DataFrame, current_upper: float, months: int = 12) -> dict | None:
    """Kỳ vọng thị trường cho lãi Fed `months` tháng tới, một thước đo duy nhất.

    Chênh = biên trên kỳ vọng ở kỳ họp cuối trong khoảng − biên trên hiện tại;
    số bước = làm tròn(chênh / 25 bps), dương là tăng.
    """
    if path is None or path.empty or pd.isna(current_upper):
        return None
    asof = path["asof"].max()
    ahead = path[
        (path["meeting_date"] > asof)
        & (path["meeting_date"] <= asof + pd.DateOffset(months=months))
    ].sort_values("meeting_date")
    if ahead.empty:
        return None
    end = ahead.iloc[-1]
    change = (float(end["exp_upper"]) - float(current_upper)) * 100
    return {
        "steps": round(change / FED_STEP_BPS),
        "end_date": pd.Timestamp(end["meeting_date"]),
        "end_upper": float(end["exp_upper"]),
        "change_bps": change,
        "asof": pd.Timestamp(asof),
        "months": months,
    }


def _fed_head(o: dict) -> str:
    n = o["steps"]
    move = f"tăng khoảng {n} lần" if n > 0 else f"giảm khoảng {-n} lần" if n < 0 else "giữ nguyên"
    return (
        f"Thị trường kỳ vọng (FedWatch) Fed {move} × 25 bps trong {o['months']} tháng tới, "
        f"về {fmt.number(o['end_upper'], 2)}% ({fmt.signed(o['change_bps'], 0)} bps so hiện tại)"
    )


def fed_summary(o: dict | None) -> str:
    """Câu tóm tắt cho bảng FedWatch (không kèm hàm ý)."""
    return f"{_fed_head(o)}, tính đến kỳ họp {o['end_date']:%d/%m/%Y}" if o else ""


def fed_note(o: dict | None) -> tuple[str, str]:
    """AI comment cho lãi Fed: dấu theo số bước kỳ vọng; một chuỗi nhân quả tới lãi suất VN."""
    if not o:
        return "", ""
    head = _fed_head(o)
    if o["steps"] > 0:
        return (
            "bad",
            f"{head} → chênh lệch lãi nghiêng về USD, áp lực tỷ giá → NHNN khó hạ lãi suất.",
        )
    if o["steps"] < 0:
        return "good", f"{head} → bớt áp lực tỷ giá VND → NHNN có thêm dư địa hạ lãi suất."
    return "", f"{head} → không thêm áp lực lên tỷ giá VND."


def implications(  # noqa: PLR0913
    card: dict,
    table: pd.DataFrame,
    names: dict[str, str],
    defaults: dict[str, dict],
    *,
    seg: str = COMMON,
    fed: dict | None = None,
    limit: int = 6,
) -> list[dict]:
    """Danh sách hàm ý: bất lợi trước (đóng góp âm nhất), rồi thuận lợi; Fed tối đa một mục.

    Dòng tham khảo (info) không có note, trừ lãi Fed (note FedWatch).
    """
    if table.empty:
        return []
    rows = {r["code"]: r for r in card.get("rows", [])}
    out, fed_done = [], False
    for rec in table.to_dict("records"):
        code = rec["code"]
        if code in FED_CODES and fed:
            if fed_done:
                continue
            tone, text = fed_note(fed)
            fed_done = True
        elif rec.get("info"):
            continue
        else:
            tone, text = note_of(
                rows.get(code, {"code": code}),
                rec.get("score"),
                defaults,
                seg,
                rec.get("measured", np.nan),
            )
        if not text:
            continue
        contrib = rec.get("contribution")
        out.append(
            {
                "code": code,
                "name": names.get(code, code),
                "label": rec.get("label") or "",
                "tone": tone,
                "text": text,
                "weight": abs(contrib) if contrib is not None and not np.isnan(contrib) else 0.0,
            }
        )
    order = {"bad": 0, "": 1, "good": 2}
    rank = lambda x: (order[x["tone"]], -x["weight"])  # noqa: E731
    fed_items = [x for x in out if x["code"] in FED_CODES]  # Fed luôn giữ lại
    rest = sorted((x for x in out if x["code"] not in FED_CODES), key=rank)
    return sorted(rest[: limit - len(fed_items)] + fed_items, key=rank)
