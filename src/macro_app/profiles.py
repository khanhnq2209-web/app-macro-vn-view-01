"""Bộ cấu hình scorecard: mỗi bộ có tên, gồm nhiều phân khúc, mỗi phân khúc có chỉ số và ngưỡng.

Lưu ở config/profiles/<bộ>/. Trang Scorecard sửa bản nháp (dict trong bộ nhớ) bằng các hàm
thuần ở cuối file, bấm Lưu mới gọi `write_profile`.
"""

from __future__ import annotations

import copy
import re
import shutil
import unicodedata
from pathlib import Path

import yaml

from macro_app.admin import THRESHOLD_KEYS, _plain
from macro_app.paths import CONFIG_DIR

PROFILES_DIR = CONFIG_DIR / "profiles"
DEFAULT_FILE = "_default.yaml"
NOTE_KEYS = ("note_bad", "note_good")  # hàm ý ghi đè câu mặc định ở config/implications.yaml
ROW_SAVE_KEYS = (
    "code",
    "pillar",
    "weight",
    "info",
    "show_level",
    "scores",
    *NOTE_KEYS,
    *THRESHOLD_KEYS,
)


def slugify(name: str, fallback: str = "bo") -> str:
    text = unicodedata.normalize("NFKD", name.replace("đ", "d").replace("Đ", "D"))
    text = text.encode("ascii", "ignore").decode()
    slug = re.sub(r"[^0-9A-Za-z]+", "_", text).strip("_").lower()[:50] or fallback
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10))}
    reserved |= {f"lpt{i}" for i in range(1, 10)}
    return f"{slug}_1" if slug in reserved else slug


def _read(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _dump(path: Path, body: dict) -> None:
    """Ghi nguyên tử: file tạm cùng thư mục rồi thay, tránh file dở dang khi lỗi giữa chừng."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(yaml.safe_dump(body, allow_unicode=True, sort_keys=False), encoding="utf-8")
    tmp.replace(path)


def clean_row(row: dict) -> dict:
    out = {k: _plain(row[k]) for k in ROW_SAVE_KEYS if k in row and row[k] is not None}
    out["code"] = row["code"]
    if out.get("window_years") is not None:
        out["window_years"] = int(out["window_years"])
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def clean_pillars(card: dict) -> list[dict]:
    """Danh sách nhóm theo thứ tự (kể cả nhóm chưa có dòng), tỷ trọng % nếu đã nhập."""
    named = [p for p in card.get("pillars") or [] if p.get("name")]
    names = [p["name"] for p in named]
    names += [r["pillar"] for r in card.get("rows", []) if r.get("pillar")]
    given = {p["name"]: p.get("weight") for p in named}
    out = []
    for name in dict.fromkeys(names):
        w = given.get(name)
        out.append({"name": name, "weight": float(w)} if w is not None else {"name": name})
    return out


def clean_card(card: dict) -> dict:
    out = {
        "name": card.get("name", ""),
        "order": int(card.get("order", 99)),
        "description": card.get("description", ""),
        "rows": [clean_row(r) for r in card.get("rows", [])],
    }
    pillars = clean_pillars(card)
    if pillars:
        out["pillars"] = pillars
    return out


def clean_profile(profile: dict) -> dict:
    return {
        "name": profile.get("name", ""),
        "order": int(profile.get("order", 99)),
        "description": profile.get("description", ""),
        "segments": {s: clean_card(c) for s, c in profile.get("segments", {}).items()},
    }


def read_profile(slug: str, folder: Path | None = None) -> dict:
    base = (folder or PROFILES_DIR) / slug
    meta = _read(base / "profile.yaml")
    segments = {}
    for path in sorted((base / "segments").glob("*.yaml")):
        data = _read(path)
        segments[path.stem] = {
            "name": data.get("name") or path.stem,
            "order": data.get("order", 99),
            "description": data.get("description", ""),
            "rows": list(data.get("rows") or []),
            "pillars": list(data.get("pillars") or []),
        }
    segments = dict(sorted(segments.items(), key=lambda kv: (kv[1]["order"], kv[1]["name"])))
    return {
        "name": meta.get("name") or slug,
        "order": meta.get("order", 99),
        "description": meta.get("description", ""),
        "segments": segments,
    }


def load_profiles(folder: Path | None = None) -> dict[str, dict]:
    root = folder or PROFILES_DIR
    if not root.exists():
        return {}
    out = {p.parent.name: read_profile(p.parent.name, root) for p in root.glob("*/profile.yaml")}
    return dict(sorted(out.items(), key=lambda kv: (kv[1]["order"], kv[1]["name"])))


def default_profile(folder: Path | None = None) -> str | None:
    root = folder or PROFILES_DIR
    names = list(load_profiles(root))
    path = root / DEFAULT_FILE
    wanted = _read(path).get("default") if path.exists() else None
    return wanted if wanted in names else (names[0] if names else None)


def write_profile(slug: str, profile: dict, folder: Path | None = None) -> Path:
    """Ghi cả bộ: profile.yaml + mỗi phân khúc một file; phân khúc đã bỏ thì xóa file."""
    base = (folder or PROFILES_DIR) / slug
    body = clean_profile(profile)
    _dump(
        base / "profile.yaml",
        {"name": body["name"], "order": body["order"], "description": body["description"]},
    )
    seg_dir = base / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    for seg, card in body["segments"].items():
        _dump(seg_dir / f"{seg}.yaml", card)
    for old in seg_dir.glob("*.yaml"):  # xóa phân khúc đã bỏ sau khi ghi xong phần còn lại
        if old.stem not in body["segments"]:
            old.unlink()
    return base


def unique_slug(name: str, taken, fallback: str = "bo") -> str:
    base = slugify(name, fallback)
    slug, i = base, 2
    while slug in taken:
        slug, i = f"{base}_{i}", i + 1
    return slug


def create_profile(
    name: str, description: str = "", source: dict | None = None, folder: Path | None = None
) -> str:
    """Bộ mới: sao chép `source` (bộ hoặc bản nháp) hoặc bộ trống. Trả slug."""
    root = folder or PROFILES_DIR
    if not name.strip():
        raise ValueError("Cần tên bộ")
    existing = load_profiles(root)
    if any(p["name"].strip().lower() == name.strip().lower() for p in existing.values()):
        raise ValueError(f"Đã có bộ tên {name}")
    slug = unique_slug(name, set(existing))
    body = copy.deepcopy(source) if source else {"segments": {}}
    body.update(
        name=name.strip(),
        description=description,
        order=max((p["order"] for p in existing.values()), default=0) + 1,
    )
    write_profile(slug, body, root)
    return slug


def delete_profile(slug: str, folder: Path | None = None) -> None:
    root = folder or PROFILES_DIR
    if len(load_profiles(root)) <= 1:
        raise ValueError("Phải giữ ít nhất một bộ")
    shutil.rmtree(root / slug)
    if default_profile(root) is None or _read(root / DEFAULT_FILE).get("default") == slug:
        set_default_profile(next(iter(load_profiles(root))), root)


def set_default_profile(slug: str, folder: Path | None = None) -> None:
    _dump((folder or PROFILES_DIR) / DEFAULT_FILE, {"default": slug})


def starter_row(code: str, direction: str | None) -> dict:
    """Dòng mới: phân vị 5 năm theo chiều của catalog (đổi sang ngưỡng cứng ở form)."""
    base = {"code": code, "method": "percentile", "window_years": 5}
    if direction == "two_way":
        return {**base, "cuts": [20, 40], "side": "both"}
    side = "below" if direction == "up_good" else "above"
    return {**base, "cuts": [10, 30, 70, 90], "side": side}


def set_row_cfg(card: dict, code: str, cfg: dict) -> dict:
    """Thay ngưỡng của một dòng, giữ trụ cột và trọng số."""
    rows = []
    for row in card.get("rows", []):
        if row["code"] == code:
            keep = {k: row.get(k) for k in ("pillar", "weight", "info", "show_level", *NOTE_KEYS)}
            row = {"code": code, **keep, **{k: v for k, v in cfg.items() if k != "code"}}
        rows.append(row)
    return {**card, "rows": rows}


def set_row_notes(card: dict, code: str, bad: str, good: str) -> dict:
    """Ghi đè hàm ý của một dòng; chuỗi rỗng = dùng câu mặc định."""
    rows = []
    for row in card.get("rows", []):
        if row["code"] == code:
            row = {k: v for k, v in row.items() if k not in NOTE_KEYS}
            row.update(
                {k: v.strip() for k, v in zip(NOTE_KEYS, (bad, good), strict=True) if v.strip()}
            )
        rows.append(row)
    return {**card, "rows": rows}


def add_segment(profile: dict, name: str, source: dict | None = None) -> tuple[dict, str]:
    if not name.strip():
        raise ValueError("Cần tên phân khúc")
    segments = profile.get("segments", {})
    if any(c["name"].strip().lower() == name.strip().lower() for c in segments.values()):
        raise ValueError(f"Đã có phân khúc tên {name}")
    slug = unique_slug(name, set(segments), "phan_khuc")
    card = copy.deepcopy(source) if source else {"description": "", "rows": []}
    card.update(
        name=name.strip(), order=max((c["order"] for c in segments.values()), default=0) + 1
    )
    return {**profile, "segments": {**segments, slug: card}}, slug


def remove_segment(profile: dict, slug: str) -> dict:
    return {**profile, "segments": {k: v for k, v in profile["segments"].items() if k != slug}}


def update_segment(profile: dict, slug: str, card: dict) -> dict:
    return {**profile, "segments": {**profile["segments"], slug: card}}


def is_dirty(draft: dict, saved: dict) -> bool:
    return clean_profile(draft) != clean_profile(saved)


# --- Sửa nhóm, dòng, tỷ trọng trên bản nháp (hàm thuần, trả card mới) ---


def _with(card: dict, *, rows: list | None = None, pillars: list | None = None) -> dict:
    out = {**card, "rows": rows if rows is not None else list(card.get("rows", []))}
    out["pillars"] = pillars if pillars is not None else clean_pillars(out)
    return out


def add_pillar(card: dict, name: str) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("Cần tên nhóm")
    if any(p["name"].strip().lower() == name.lower() for p in clean_pillars(card)):
        raise ValueError(f"Đã có nhóm tên {name}")
    return _with(card, pillars=[*clean_pillars(card), {"name": name}])


def rename_pillar(card: dict, old: str, new: str) -> dict:
    new = new.strip()
    if not new or new == old:
        return card
    if any(p["name"] == new for p in clean_pillars(card)):
        raise ValueError(f"Đã có nhóm tên {new}")
    rows = [{**r, "pillar": new} if r.get("pillar") == old else r for r in card.get("rows", [])]
    pillars = [{**p, "name": new} if p["name"] == old else p for p in clean_pillars(card)]
    return _with(card, rows=rows, pillars=pillars)


def remove_pillar(card: dict, name: str) -> dict:
    rows = [r for r in card.get("rows", []) if r.get("pillar") != name]
    pillars = [p for p in clean_pillars(card) if p["name"] != name]
    return _with(card, rows=rows, pillars=pillars)


def set_pillar_weight(card: dict, name: str, weight: float | None) -> dict:
    pillars = [
        (
            {"name": p["name"], "weight": float(weight)}
            if weight is not None
            else {"name": p["name"]}
        )
        if p["name"] == name
        else p
        for p in clean_pillars(card)
    ]
    return _with(card, pillars=pillars)


def set_row_weight(card: dict, code: str, weight: float | None) -> dict:
    rows = []
    for r in card.get("rows", []):
        if r["code"] == code:
            r = {k: v for k, v in r.items() if k != "weight"}
            if weight is not None:
                r["weight"] = float(weight)
        rows.append(r)
    return _with(card, rows=rows)


def reset_weights(card: dict, pillar: str | None = None) -> dict:
    """Bỏ tỷ trọng đã nhập (chia đều lại): cả phân khúc, hoặc chỉ trong một nhóm."""
    rows = [
        {k: v for k, v in r.items() if k != "weight"} if pillar in (None, r.get("pillar")) else r
        for r in card.get("rows", [])
    ]
    pillars = clean_pillars(card)
    if pillar is None:
        pillars = [{"name": p["name"]} for p in pillars]
    return _with(card, rows=rows, pillars=pillars)


def add_row(card: dict, row: dict, pillar: str) -> dict:
    if any(r["code"] == row["code"] for r in card.get("rows", [])):
        raise ValueError("Chỉ số đã có trong phân khúc")
    return _with(card, rows=[*card.get("rows", []), {**row, "pillar": pillar}])


def remove_row(card: dict, code: str) -> dict:
    return _with(card, rows=[r for r in card.get("rows", []) if r["code"] != code])


def move_row(card: dict, code: str, pillar: str) -> dict:
    rows = [
        {**{k: v for k, v in r.items() if k != "weight"}, "pillar": pillar}
        if r["code"] == code and r.get("pillar") != pillar
        else r
        for r in card.get("rows", [])
    ]
    return _with(card, rows=rows)


# --- Kiểm tra bản nháp trước khi lưu (checklist bước 4 trang Cấu hình) ---


def check_profile(
    draft: dict, catalog: dict, settings: dict, *, unconfirmed=(), other_names=()
) -> list[dict]:
    """Mỗi mục: {ok, text, step}. Lưu được khi mọi mục ok."""
    from macro_app.metrics import scorecard as sc

    name = draft.get("name", "").strip()
    taken = {n.strip().lower() for n in other_names}
    segs = draft.get("segments", {})
    empty, weight, cuts = [], [], []
    for card in segs.values():
        label = card.get("name", "")
        werr = sc.weight_errors(card, catalog)
        scored = [r for r in card.get("rows", []) if r.get("code") in catalog and not r.get("info")]
        if not clean_pillars(card) or not scored:
            empty.append(f"{label}: chưa có nhóm hoặc chỉ số tính điểm")
        empty += [f"{label}: {e}" for e in werr if "chưa có chỉ số" in e]
        weight += [f"{label}: {e}" for e in werr if "chưa có chỉ số" not in e]
        rows_only = sc.validate_card({"rows": card.get("rows", [])}, catalog, settings)
        cuts += [f"{label}: {e}" for e in rows_only if "tỷ trọng" not in e]
    n_unconf = len(list(unconfirmed))
    return [
        {"ok": bool(name), "text": "Scorecard có tên", "step": 1},
        {
            "ok": name.lower() not in taken,
            "text": "Tên chưa trùng bộ khác"
            if name.lower() not in taken
            else f"Đã có bộ tên {name}",
            "step": 1,
        },
        {"ok": bool(segs), "text": "Có ít nhất 1 phân khúc", "step": 1},
        {
            "ok": not empty,
            "text": empty[0] if empty else "Mỗi nhóm có ít nhất 1 chỉ số tính điểm",
            "step": 2,
        },
        {
            "ok": not weight,
            "text": weight[0] if weight else "Tỷ trọng mỗi cấp cộng đủ 100%",
            "step": 2,
        },
        {"ok": not cuts, "text": cuts[0] if cuts else "Mốc mỗi chỉ số hợp lệ", "step": 3},
        {
            "ok": not n_unconf,
            "text": f"Còn {n_unconf} chỉ số chưa xác nhận mốc"
            if n_unconf
            else "Đã xác nhận mốc mọi chỉ số mới thêm",
            "step": 3,
        },
    ]
