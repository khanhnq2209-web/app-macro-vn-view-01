"""Bộ cấu hình scorecard: đọc/ghi, bản nháp, sao chép, mặc định."""

import pytest

from macro_app import profiles as pf

ROW = {
    "code": "cpi_yoy",
    "pillar": "Lạm phát",
    "method": "absolute",
    "cuts": [2.5, 3.5, 4.5, 5.5],
    "side": "above",
}


def sample():
    return {
        "name": "Thử",
        "order": 1,
        "description": "bộ thử",
        "segments": {"nha_o": {"name": "Nhà ở", "order": 1, "description": "", "rows": [ROW]}},
    }


def test_write_read_roundtrip_and_removed_segment_deleted(tmp_path):
    pf.write_profile("thu", sample(), tmp_path)
    got = pf.read_profile("thu", tmp_path)
    assert got["name"] == "Thử" and got["segments"]["nha_o"]["rows"][0]["cuts"] == [
        2.5,
        3.5,
        4.5,
        5.5,
    ]
    assert not pf.is_dirty(got, sample())
    two, slug = pf.add_segment(got, "KCN")
    pf.write_profile("thu", two, tmp_path)
    assert (tmp_path / "thu" / "segments" / f"{slug}.yaml").exists()
    pf.write_profile("thu", pf.remove_segment(two, slug), tmp_path)
    assert not (tmp_path / "thu" / "segments" / f"{slug}.yaml").exists()


def test_draft_edits_keep_pillar_weight_and_mark_dirty():
    saved = sample()
    card = {**saved["segments"]["nha_o"], "rows": [{**ROW, "weight": 2.0}]}
    card = pf.set_row_cfg(
        card, "cpi_yoy", {"method": "absolute", "cuts": [3, 4, 5, 6], "side": "above"}
    )
    assert card["rows"][0]["pillar"] == "Lạm phát" and card["rows"][0]["weight"] == 2.0
    assert card["rows"][0]["cuts"] == [3, 4, 5, 6]
    draft = pf.update_segment(saved, "nha_o", card)
    assert pf.is_dirty(draft, saved)
    assert saved["segments"]["nha_o"]["rows"] == [ROW]  # bản đã lưu không bị đổi theo


def test_add_segment_rejects_duplicate_name():
    with pytest.raises(ValueError):
        pf.add_segment(sample(), "nhà ở")


def test_create_copy_default_delete(tmp_path):
    pf.write_profile("thu", sample(), tmp_path)
    slug = pf.create_profile("Bản thận trọng", "", sample(), tmp_path)
    assert pf.read_profile(slug, tmp_path)["segments"]["nha_o"]["rows"][0]["code"] == "cpi_yoy"
    with pytest.raises(ValueError):
        pf.create_profile("bản thận trọng", folder=tmp_path)
    blank = pf.create_profile("Trống", folder=tmp_path)
    assert pf.read_profile(blank, tmp_path)["segments"] == {}
    pf.set_default_profile(slug, tmp_path)
    assert pf.default_profile(tmp_path) == slug
    pf.delete_profile(slug, tmp_path)
    assert slug not in pf.load_profiles(tmp_path)
    assert pf.default_profile(tmp_path) in pf.load_profiles(tmp_path)


def test_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    pf.write_profile("thu", sample(), tmp_path)
    assert not list(tmp_path.rglob("*.tmp"))


def test_reserved_windows_names_get_safe_slug():
    assert pf.slugify("CON") != "con"
    assert pf.slugify("nul") != "nul"
    assert pf.slugify("Nhà ở") == "nha_o"


def test_bool_survives_admin_plain():
    from macro_app.admin import _plain

    assert _plain({"ytd": True}) == {"ytd": True}
