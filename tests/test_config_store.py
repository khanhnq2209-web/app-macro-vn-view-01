"""Kho cấu hình dùng chung: lưu thêm dòng, chống ghi đè, lịch sử, hoàn tác, bản gốc YAML."""

import json

import pytest

from macro_app import config_store as cs


def prof(name="Bộ A", cut=4.5):
    return {
        "name": name,
        "order": 1,
        "description": "",
        "segments": {
            "nha_o": {
                "name": "Nhà ở",
                "order": 1,
                "description": "",
                "rows": [{"code": "cpi_yoy", "pillar": "Ổn định", "cuts": [2.5, 3.5, cut, 5.5]}],
            }
        },
    }


SEED = {"bo_a": prof()}


def test_seed_used_until_first_save_then_store_wins():
    store = cs.MemoryStore()
    assert cs.load_profiles(store.rows(), SEED)["bo_a"]["name"] == "Bộ A"
    assert cs.version_of(store.rows(), "bo_a") == 0
    v = cs.save(store, "bo_a", prof(cut=4.0), base=0, by="Lan")
    assert v == 1
    got = cs.load_profiles(store.rows(), SEED)["bo_a"]
    assert got["segments"]["nha_o"]["rows"][0]["cuts"][2] == 4.0
    assert cs.meta(store.rows())["bo_a"]["saved_by"] == "Lan"


def test_second_editor_with_old_version_gets_conflict_not_overwrite():
    store = cs.MemoryStore()
    cs.save(store, "bo_a", prof(cut=4.0), base=0, by="Lan")
    with pytest.raises(cs.ConflictError):
        cs.save(store, "bo_a", prof(cut=3.9), base=0, by="Minh")  # Minh mở trước khi Lan lưu
    assert len(store.rows()) == 1
    cs.save(store, "bo_a", prof(cut=3.9), base=1, by="Minh")  # tải lại rồi lưu
    assert cs.version_of(store.rows(), "bo_a") == 2


def test_history_and_restore_old_version():
    store = cs.MemoryStore()
    cs.save(store, "bo_a", prof(cut=4.0), base=0, by="Lan")
    cs.save(store, "bo_a", prof(cut=9.0), base=1, by="Ai đó")  # sửa nhầm
    hist = cs.versions(store.rows(), "bo_a")
    assert [h["version"] for h in hist] == [2, 1] and hist[0]["by"] == "Ai đó"
    cs.restore(store, "bo_a", 1, base=2, by="Lan")
    got = cs.load_profiles(store.rows(), SEED)["bo_a"]
    assert got["segments"]["nha_o"]["rows"][0]["cuts"][2] == 4.0
    assert cs.version_of(store.rows(), "bo_a") == 3


def test_delete_hides_profile_even_from_seed_and_default_falls_back():
    store = cs.MemoryStore()
    cs.save(store, "bo_b", prof("Bộ B"), base=0, by="Lan")
    cs.set_default(store, "bo_b", by="Lan")
    loaded = cs.load_profiles(store.rows(), SEED)
    assert cs.default_slug(store.rows(), loaded, "bo_a") == "bo_b"
    cs.delete(store, "bo_b", base=1, by="Lan")
    loaded = cs.load_profiles(store.rows(), SEED)
    assert "bo_b" not in loaded
    assert cs.default_slug(store.rows(), loaded, "bo_a") == "bo_a"


def test_payload_size_limit_and_new_slug_never_reuses_deleted():
    store = cs.MemoryStore()
    huge = prof()
    huge["description"] = "x" * (cs.MAX_PAYLOAD + 1)
    with pytest.raises(ValueError, match="quá lớn"):
        cs.save(store, "bo_a", huge, base=0, by="Lan")
    cs.save(store, "bo_moi", prof("Bộ mới"), base=0, by="Lan")
    cs.delete(store, "bo_moi", base=1, by="Lan")
    loaded = cs.load_profiles(store.rows(), SEED)
    assert cs.new_slug("Bộ mới", store.rows(), loaded) == "bo_moi_2"


def test_saved_payload_is_clean_json_with_pillars():
    store = cs.MemoryStore()
    p = prof()
    p["segments"]["nha_o"]["pillars"] = [{"name": "Ổn định", "weight": 100}]
    cs.save(store, "bo_a", p, base=0, by="Lan")
    body = json.loads(store.rows()[0]["payload"])
    assert body["segments"]["nha_o"]["pillars"] == [{"name": "Ổn định", "weight": 100.0}]


def test_file_store_roundtrip(tmp_path):
    store = cs.FileStore(tmp_path / "v.jsonl")
    cs.save(store, "bo_a", prof(cut=4.0), base=0, by="Lan")
    again = cs.FileStore(tmp_path / "v.jsonl")
    assert cs.version_of(again.rows(), "bo_a") == 1


def test_store_mode_from_env(monkeypatch):
    monkeypatch.setenv("CONFIG_STORE", "memory")
    assert isinstance(cs.make_store({"gsheets": {"spreadsheet": "x"}}), cs.MemoryStore)
    monkeypatch.setenv("CONFIG_STORE", "")
    assert isinstance(cs.make_store({}), cs.FileStore)


@pytest.mark.live
def test_live_sheet_append_and_read():
    """Gọi Google Sheets thật: ghi 1 dòng bộ `_kiem_tra` rồi đọc lại (chạy: pytest -m live)."""
    secrets = cs.read_secrets()
    if not (secrets.get("gsheets") or {}).get("spreadsheet"):
        pytest.skip("chưa có [gsheets] trong secrets")
    sheet = secrets["gsheets"]
    store = cs.SheetStore(
        {k: v for k, v in sheet.items() if k != "spreadsheet"}, sheet["spreadsheet"]
    )
    base = cs.version_of(store.rows(), "_kiem_tra")
    v = cs.save(store, "_kiem_tra", prof("Kiểm tra kết nối"), base=base, by="pytest")
    assert cs.version_of(store.rows(), "_kiem_tra") == v
    cs.delete(store, "_kiem_tra", base=v, by="pytest")


class RacingStore(cs.MemoryStore):
    """Người khác ghi xen vào đúng lúc mình đang lưu (cùng đọc v1, cùng ghi v2)."""

    def __init__(self, other: dict) -> None:
        super().__init__()
        self.other = other

    def append(self, row: dict) -> None:
        if self.other:
            super().append(self.other)
            self.other = None
        super().append(row)


def test_simultaneous_save_first_writer_wins_second_gets_conflict():
    store = RacingStore(None)
    cs.save(store, "bo_a", prof(cut=4.0), base=0, by="Lan")  # v1
    store.other = {
        "bo_id": "bo_a",
        "version": 2,
        "status": "saved",
        "payload": __import__("json").dumps(prof(cut=3.0)),
        "saved_by": "Minh",
        "saved_at": "x",
    }
    with pytest.raises(cs.ConflictError):
        cs.save(store, "bo_a", prof(cut=9.0), base=1, by="Lan")
    current = cs.load_profiles(store.rows(), SEED)["bo_a"]
    assert current["segments"]["nha_o"]["rows"][0]["cuts"][2] == 3.0  # bản của Minh
    assert [v["version"] for v in cs.versions(store.rows(), "bo_a")] == [2, 1]  # không trùng


def test_corrupt_row_is_skipped_not_crash():
    store = cs.MemoryStore()
    cs.save(store, "bo_a", prof(cut=4.0), base=0, by="Lan")
    store.append({"bo_id": "bo_a", "version": 2, "status": "saved", "payload": "{hỏng"})
    store.append({"bo_id": cs.DEFAULT_ID, "version": 1, "status": "default", "payload": "x"})
    loaded = cs.load_profiles(store.rows(), SEED)
    assert loaded["bo_a"]["name"] == "Bộ A"  # dòng hỏng bị bỏ qua, dùng bản gốc
    assert cs.default_slug(store.rows(), loaded, "bo_a") == "bo_a"


def test_current_version_ignores_sheet_row_order():
    store = cs.MemoryStore()
    cs.save(store, "bo_a", prof(cut=4.0), base=0, by="Lan")
    cs.save(store, "bo_a", prof(cut=3.0), base=1, by="Lan")
    rows = list(reversed(store.rows()))  # ai đó sắp xếp lại Sheet
    assert cs.version_of(rows, "bo_a") == 2
    assert cs.load_profiles(rows, SEED)["bo_a"]["segments"]["nha_o"]["rows"][0]["cuts"][2] == 3.0


def test_deleted_profile_can_be_restored():
    store = cs.MemoryStore()
    cs.save(store, "bo_b", prof("Bộ B"), base=0, by="Lan")
    cs.delete(store, "bo_b", base=1, by="Lan")
    gone = cs.deleted(store.rows())
    assert gone == {"bo_b": {"name": "Bộ B", "version": 1}}
    cs.restore(store, "bo_b", 1, base=2, by="Lan")
    assert "bo_b" in cs.load_profiles(store.rows(), SEED) and not cs.deleted(store.rows())


def test_segments_keep_their_order_after_roundtrip():
    """JSON trên kho lưu sort_keys (kcn < nha_o); đọc lại phải theo `order` của phân khúc."""
    store = cs.MemoryStore()
    prof = {
        "name": "BĐS",
        "order": 1,
        "segments": {
            "nha_o": {"name": "Nhà ở", "order": 1, "rows": []},
            "kcn": {"name": "KCN", "order": 2, "rows": []},
        },
    }
    cs.save(store, "bo", prof, base=0, by="t")
    assert list(cs.load_profiles(store.rows(), {})["bo"]["segments"]) == ["nha_o", "kcn"]
