"""Nghiệm thu #7: view lưu, khôi phục, xuất/nhập YAML."""

import copy

import pytest

from macro_app import views
from macro_app.config import load_catalog

KNOWN = {i.code for i in load_catalog()}


def test_default_view_is_valid():
    assert views.validate(views.load_default(), KNOWN) == []


def test_custom_view_yaml_roundtrip_and_save(tmp_path):
    view = {**copy.deepcopy(views.load_default()), "name": "Test"}
    view["overview"]["blocks"][0]["codes"].remove("dxy")
    view["vietnam"]["charts"][0].update(transform="yoy", range="3Y")
    assert views.from_yaml(views.to_yaml(view)) == view
    views.save_shared(view, views_dir=tmp_path)
    assert views.list_shared(tmp_path)["Test"] == view


def test_default_view_cannot_be_overwritten(tmp_path):
    with pytest.raises(ValueError):
        views.save_shared(views.load_default(), views_dir=tmp_path)


def test_view_validation_rejects_unknown_code():
    view = {**copy.deepcopy(views.load_default()), "name": "X"}
    view["international"]["charts"][0]["codes"] = ["khong_co"]
    assert any("khong_co" in e for e in views.validate(view, KNOWN))


def test_threshold_sets_save_activate_and_merge(tmp_path):
    import shutil

    from macro_app import admin
    from macro_app.config import active_threshold_sets, load_threshold_sets, load_thresholds
    from macro_app.paths import CONFIG_DIR

    cfg_dir = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, cfg_dir, ignore=shutil.ignore_patterns("threshold_sets"))
    sets_dir = cfg_dir / "threshold_sets"
    items = {"vix": {"method": "absolute", "cuts": [15.0, 20.0, 30.0], "side": "above"}}
    admin.save_threshold_set("Bộ thử", "mô tả", items, folder=sets_dir)
    assert load_threshold_sets(cfg_dir)["bo_thu"]["name"] == "Bộ thử"
    admin.set_active_threshold_sets(["bo_thu"], folder=sets_dir)
    assert active_threshold_sets(cfg_dir) == ["bo_thu"]
    _, overrides = load_thresholds(cfg_dir)
    assert overrides["vix"]["cuts"] == [15.0, 20.0, 30.0]
    assert overrides["vix"]["_file"] == "bộ: Bộ thử"


def test_bundled_threshold_sets_are_valid():
    from macro_app.config import load_threshold_sets
    from macro_app.metrics.status import validate_cfg

    sets = load_threshold_sets()
    assert len(sets) >= 2
    for s in sets.values():
        assert 8 <= len(s["items"]) <= 10
        for code, cfg in s["items"].items():
            assert code in KNOWN
            assert validate_cfg(cfg) == [], (code, validate_cfg(cfg))
