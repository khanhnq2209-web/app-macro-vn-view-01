"""Kho bộ cấu hình scorecard dùng chung, có lịch sử phiên bản (Google Sheets khi deploy).

Mỗi lần lưu THÊM một dòng (không sửa dòng cũ):
    bo_id | version | status | payload | saved_by | saved_at | approved_by | approved_at
status: `saved` (payload = JSON bộ), `deleted`, `default` (bo_id `_default`, payload {"default"}).
Bản hiện hành của một bộ = dòng cuối của bộ đó. Bộ chưa có dòng nào thì dùng YAML trong
config/profiles/ (bản gốc trong repo). Lưu kèm số phiên bản đang sửa: kho đã có bản mới hơn thì
báo xung đột thay vì ghi đè.
"""

from __future__ import annotations

import json
import os
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from macro_app import profiles as pf
from macro_app.paths import ROOT

HEADERS = [
    "bo_id",
    "version",
    "status",
    "payload",
    "saved_by",
    "saved_at",
    "approved_by",
    "approved_at",
]
DEFAULT_ID = "_default"
MAX_PAYLOAD = 45_000  # ô Google Sheets tối đa 50.000 ký tự
FILE_STORE = ROOT / "config" / "profile_versions.jsonl"


class ConflictError(Exception):
    """Kho đã có phiên bản mới hơn bản đang sửa."""


class Store(Protocol):
    def rows(self) -> list[dict]: ...
    def append(self, row: dict) -> None: ...


class MemoryStore:
    """Kho trong bộ nhớ, cho test."""

    def __init__(self) -> None:
        self._rows: list[dict] = []

    def rows(self) -> list[dict]:
        return [dict(r) for r in self._rows]

    def append(self, row: dict) -> None:
        self._rows.append({h: row.get(h, "") for h in HEADERS})


class FileStore:
    """Kho JSON Lines trên máy (chạy local không có Google Sheets)."""

    def __init__(self, path: Path = FILE_STORE) -> None:
        self.path = path

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(x) for x in lines if x.strip()]

    def append(self, row: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({h: row.get(h, "") for h in HEADERS}, ensure_ascii=False) + "\n")


class SheetStore:
    """Tab `versions` của Google Sheet, đọc/ghi bằng service account."""

    def __init__(self, info: dict, url: str, worksheet: str = "versions") -> None:
        import gspread

        client = gspread.service_account_from_dict(info)
        self._ws = client.open_by_url(url).worksheet(worksheet)

    def rows(self) -> list[dict]:
        return self._ws.get_all_records(expected_headers=HEADERS, numericise_ignore=["all"])

    def append(self, row: dict) -> None:
        self._ws.append_row([row.get(h, "") for h in HEADERS], value_input_option="RAW")


def read_secrets(path: Path | None = None) -> dict:
    path = path or ROOT / ".streamlit" / "secrets.toml"
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def make_store(secrets: dict) -> Store:
    """CONFIG_STORE=sheets|file|memory; mặc định sheets nếu có mục [gsheets], không thì file."""
    mode = os.getenv("CONFIG_STORE", "").strip().lower()
    sheet = secrets.get("gsheets") or {}
    if not mode:
        mode = "sheets" if sheet.get("spreadsheet") else "file"
    if mode == "memory":
        return MemoryStore()
    if mode == "sheets":
        info = {k: v for k, v in sheet.items() if k != "spreadsheet"}
        return SheetStore(info, sheet["spreadsheet"])
    return FileStore()


def _int(x) -> int:
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def _latest(rows: list[dict]) -> dict[str, dict]:
    """Dòng hiện hành của mỗi bộ: phiên bản lớn nhất; trùng số thì dòng ghi trước thắng.

    Không phụ thuộc thứ tự dòng (ai đó sắp xếp lại Sheet vẫn đúng). Hai người lưu cùng lúc
    ra trùng số phiên bản thì người sau nhận báo xung đột (xem `_append`).
    """
    out: dict[str, dict] = {}
    for r in rows:
        key = str(r.get("bo_id"))
        if key not in out or _int(r.get("version")) > _int(out[key].get("version")):
            out[key] = r
    return out


def _payload(r: dict) -> dict | None:
    """JSON của dòng; dòng hỏng (ai đó sửa tay Sheet) thì bỏ qua thay vì làm sập trang."""
    try:
        body = json.loads(r.get("payload") or "")
    except (TypeError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def version_of(rows: list[dict], bo_id: str) -> int:
    """Phiên bản hiện hành (0 = chưa có trên kho, đang dùng bản gốc YAML hoặc bộ mới)."""
    last = _latest(rows).get(bo_id)
    return _int(last["version"]) if last else 0


def load_profiles(rows: list[dict], seed: dict[str, dict]) -> dict[str, dict]:
    """Bộ hiện hành: bản gốc YAML, đè bằng bản mới nhất trên kho, bỏ bộ đã xóa."""
    out = {slug: prof for slug, prof in seed.items()}
    for bo_id, r in _latest(rows).items():
        if bo_id == DEFAULT_ID:
            continue
        if r.get("status") == "deleted":
            out.pop(bo_id, None)
        elif r.get("status") == "saved" and (body := _payload(r)) and "segments" in body:
            # JSON lưu sort_keys nên phân khúc theo tên; xếp lại theo thứ tự đã đặt
            segs = body["segments"].items()
            body["segments"] = dict(sorted(segs, key=lambda kv: (kv[1].get("order", 99), kv[0])))
            out[bo_id] = body
    return dict(sorted(out.items(), key=lambda kv: (kv[1].get("order", 99), kv[1].get("name", ""))))


def meta(rows: list[dict]) -> dict[str, dict]:
    """Người và lúc lưu bản hiện hành của từng bộ."""
    return {
        bo_id: {"version": _int(r["version"]), "saved_by": r["saved_by"], "saved_at": r["saved_at"]}
        for bo_id, r in _latest(rows).items()
        if bo_id != DEFAULT_ID and r.get("status") == "saved"
    }


def default_slug(rows: list[dict], loaded: dict[str, dict], seed_default: str | None) -> str | None:
    last = _latest(rows).get(DEFAULT_ID)
    wanted = (_payload(last) or {}).get("default") if last else seed_default
    return wanted if wanted in loaded else next(iter(loaded), None)


def versions(rows: list[dict], bo_id: str) -> list[dict]:
    """Lịch sử một bộ, mới nhất trước."""
    seen: set[int] = set()
    keep = []
    for r in rows:  # trùng số phiên bản (hai người lưu cùng lúc): giữ dòng ghi trước
        if str(r.get("bo_id")) == bo_id and _int(r["version"]) not in seen:
            seen.add(_int(r["version"]))
            keep.append(r)
    keep.sort(key=lambda r: _int(r["version"]))
    return [
        {
            "version": _int(r["version"]),
            "status": r["status"],
            "by": r["saved_by"],
            "at": r["saved_at"],
        }
        for r in reversed(keep)
    ]


def payload_at(rows: list[dict], bo_id: str, version: int) -> dict:
    for r in rows:
        if str(r.get("bo_id")) == bo_id and _int(r["version"]) == version and _payload(r):
            return _payload(r)
    raise KeyError(f"{bo_id} không có phiên bản {version}")


VN_TIME = timezone(timedelta(hours=7))  # máy chủ cloud chạy giờ UTC


def _now() -> str:
    return datetime.now(VN_TIME).replace(microsecond=0, tzinfo=None).isoformat(sep=" ")


def _append(store: Store, bo_id: str, status: str, payload: str, *, base: int, by: str) -> int:  # noqa: PLR0913
    rows = store.rows()  # đọc mới để kiểm xung đột
    current = version_of(rows, bo_id)
    if current != base:
        raise ConflictError(
            f"Bộ đã được lưu bởi người khác (phiên bản {current}). Tải lại rồi sửa tiếp."
        )
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("Cấu hình quá lớn để lưu")
    new = max([_int(r["version"]) for r in rows if str(r.get("bo_id")) == bo_id], default=0) + 1
    mine = {
        "bo_id": bo_id,
        "version": new,
        "status": status,
        "payload": payload,
        "saved_by": by.strip()[:60],
        "saved_at": _now(),
    }
    store.append(mine)
    # Hai người cùng đọc v(n) rồi cùng ghi v(n+1): dòng ghi trước thắng (_latest), người sau
    # được báo để tải lại thay vì tưởng đã lưu.
    first = next(
        r for r in store.rows() if str(r.get("bo_id")) == bo_id and _int(r.get("version")) == new
    )
    if (first.get("saved_by"), first.get("saved_at"), first.get("payload")) != (
        mine["saved_by"],
        mine["saved_at"],
        mine["payload"],
    ):
        raise ConflictError("Có người vừa lưu bộ này cùng lúc với bạn. Tải lại rồi sửa tiếp.")
    return new


def save(store: Store, bo_id: str, profile: dict, *, base: int, by: str) -> int:
    body = json.dumps(pf.clean_profile(profile), ensure_ascii=False, sort_keys=True)
    return _append(store, bo_id, "saved", body, base=base, by=by)


def delete(store: Store, bo_id: str, *, base: int, by: str) -> int:
    return _append(store, bo_id, "deleted", "", base=base, by=by)


def restore(store: Store, bo_id: str, version: int, *, base: int, by: str) -> int:
    """Hoàn tác: lưu lại nội dung phiên bản cũ thành phiên bản mới."""
    return save(store, bo_id, payload_at(store.rows(), bo_id, version), base=base, by=by)


def set_default(store: Store, bo_id: str, *, by: str) -> None:
    rows = store.rows()
    _append(
        store,
        DEFAULT_ID,
        "default",
        json.dumps({"default": bo_id}),
        base=version_of(rows, DEFAULT_ID),
        by=by,
    )


def new_slug(name: str, rows: list[dict], loaded: dict[str, dict]) -> str:
    """Slug chưa dùng (kể cả bộ đã xóa, để lịch sử không trộn)."""
    taken = set(loaded) | {str(r.get("bo_id")) for r in rows}
    return pf.unique_slug(name, taken)


def deleted(rows: list[dict]) -> dict[str, dict]:
    """Bộ đã xóa còn phiên bản đã lưu để khôi phục: {bo_id: {name, version}}."""
    out = {}
    for bo_id, last in _latest(rows).items():
        if last.get("status") != "deleted":
            continue
        saved = [v for v in versions(rows, bo_id) if v["status"] == "saved"]
        if saved:
            body = payload_at(rows, bo_id, saved[0]["version"])
            out[bo_id] = {"name": body.get("name", bo_id), "version": saved[0]["version"]}
    return out
