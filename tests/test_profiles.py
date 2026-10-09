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


def _card():
    return {
        "name": "Nhà ở",
        "rows": [
            {
                "code": "cpi_yoy",
                "pillar": "Giá",
                "method": "absolute",
                "cuts": [2.5, 3.5, 4.5, 5.5],
            },
            {"code": "pmi_vn", "pillar": "Cầu", "method": "absolute", "cuts": [47, 49, 50, 52]},
        ],
    }


def test_pillar_edits_keep_order_and_empty_groups():
    card = pf.add_pillar(_card(), "Hạ tầng")
    assert [p["name"] for p in pf.clean_pillars(card)] == ["Giá", "Cầu", "Hạ tầng"]
    card = pf.rename_pillar(card, "Giá", "Giá cả")
    assert card["rows"][0]["pillar"] == "Giá cả"
    card = pf.set_pillar_weight(card, "Cầu", 60)
    card = pf.set_row_weight(card, "cpi_yoy", 100)
    assert {"name": "Cầu", "weight": 60.0} in pf.clean_pillars(card)
    assert pf.reset_weights(card)["rows"][0].get("weight") is None
    assert all("weight" not in p for p in pf.clean_pillars(pf.reset_weights(card)))
    card = pf.move_row(card, "pmi_vn", "Hạ tầng")
    assert card["rows"][1]["pillar"] == "Hạ tầng"
    card = pf.remove_pillar(card, "Hạ tầng")
    assert [r["code"] for r in card["rows"]] == ["cpi_yoy"]
    with pytest.raises(ValueError):
        pf.add_pillar(card, "giá cả")


def test_saved_card_keeps_pillars(tmp_path):
    prof = {"name": "Thử", "segments": {"nha_o": pf.add_pillar(_card(), "Trống")}}
    pf.write_profile("thu", prof, tmp_path)
    got = pf.read_profile("thu", tmp_path)["segments"]["nha_o"]
    assert [p["name"] for p in got["pillars"]] == ["Giá", "Cầu", "Trống"]


def test_check_profile_lists_what_blocks_saving():
    from macro_app.config import load_catalog
    from macro_app.metrics.scorecard import load_settings

    cat = {i.code: i for i in load_catalog()}
    settings = load_settings()
    draft = {"name": "", "segments": {"nha_o": pf.add_pillar(_card(), "Trống")}}
    res = pf.check_profile(draft, cat, settings, unconfirmed={"nha_o/pmi_vn"}, other_names=["Bộ A"])
    bad = {r["text"] for r in res if not r["ok"]}
    assert "Scorecard có tên" in bad
    assert any("Trống" in t for t in bad)
    assert any("chưa xác nhận" in t for t in bad)
    draft = {"name": "bộ a", "segments": {"nha_o": _card()}}
    res = pf.check_profile(draft, cat, settings, other_names=["Bộ A"])
    assert [r["text"] for r in res if not r["ok"]] == ["Đã có bộ tên bộ a"]
    draft["name"] = "Bộ B"
    assert all(r["ok"] for r in pf.check_profile(draft, cat, settings, other_names=["Bộ A"]))


def test_every_bundled_profile_is_valid():
    """3 bộ có sẵn (BĐS, Tỷ giá và Lãi suất, Giá năng lượng) qua được checklist lưu."""
    from macro_app.config import load_catalog
    from macro_app.metrics.scorecard import load_settings

    cat = {i.code: i for i in load_catalog()}
    profiles = pf.load_profiles()
    assert set(profiles) == {"theo_doi_bds_01", "theo_doi_ty_gia_lai_suat", "theo_doi_dau_khi"}
    for slug, prof in profiles.items():
        others = [p["name"] for s, p in profiles.items() if s != slug]
        res = pf.check_profile(prof, cat, load_settings(), other_names=others)
        assert all(r["ok"] for r in res), (slug, [r["text"] for r in res if not r["ok"]])
