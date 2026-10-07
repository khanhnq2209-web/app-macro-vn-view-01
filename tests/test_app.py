"""AppTest: mọi trang chạy không lỗi; Tổng quan khớp latest; chế độ công khai không có nút ghi."""

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from macro_app.paths import APP_DIR

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    "overview",
    "international",
    "vietnam",
    "scorecard",
    "scorecard_config",
    "forecasts",
    "thresholds",
    "views_editor",
    "detail",
]
pytestmark = pytest.mark.skipif(
    not (APP_DIR / "latest.parquet").exists(), reason="chưa build data/app"
)


def run_page(page: str, admin: bool = False) -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.session_state["is_admin"] = admin
    at.session_state["admin_name"] = "test"
    at.run()
    if page != "scorecard":  # trang mặc định
        at.switch_page(f"app_pages/{page}.py").run()
    return at


@pytest.mark.parametrize("page", PAGES)
def test_page_runs_without_exception(page):
    admin = page in (
        "scorecard_config",
        "thresholds",
        "views_editor",
    )  # nhóm Cấu hình: chỉ quản trị
    at = run_page(page, admin=admin)
    assert not at.exception, [e.value for e in at.exception]


def test_overview_cards_match_latest():
    at = run_page("overview")
    html = " ".join(h.proto.body for h in at.get("html"))
    latest = pd.read_parquet(APP_DIR / "latest.parquet")
    with_data = latest[latest["value"].notna()]
    shown = [n for n in with_data["name"] if n in html]
    assert len(shown) >= 15
    assert html.count("detail?code=") >= 20  # mỗi dòng có link sang trang chi tiết
    assert "05/10/2026" in html or "06/10/2026" in html  # kỳ dữ liệu hiển thị dd/mm/yyyy


def test_public_mode_has_no_write_controls():
    """Bản công khai: không có nhóm menu Cấu hình, không có nút ghi."""
    at = run_page("overview", admin=False)
    assert "Refresh dữ liệu" not in [b.label for b in at.sidebar.button]


def test_admin_sees_save():
    at = run_page("thresholds", admin=True)
    assert "Về ngưỡng mặc định" in [b.label for b in at.button]


@pytest.fixture
def save_calls(monkeypatch):
    """Ghi lại mọi lần lưu (ngưỡng, bộ cấu hình) thay vì ghi file thật."""
    from macro_app import admin, build, profiles
    from macro_app.ui import threshold_form

    calls = []
    for mod, name in (
        (admin, "save_threshold"),
        (profiles, "write_profile"),
        (profiles, "create_profile"),
        (profiles, "delete_profile"),
        (profiles, "set_default_profile"),
    ):
        monkeypatch.setattr(mod, name, lambda *a, _n=name, **k: calls.append((_n, a[:1])))
    monkeypatch.setattr(build, "rescore", lambda *a, **k: {})
    monkeypatch.setattr(threshold_form, "rescore", lambda *a, **k: {})
    return calls


def _sample_codes() -> list[str]:
    """Một mã cho mỗi kiểu ngưỡng (và có/không biến đổi) đang cấu hình."""
    from macro_app.ui.threshold_editor import current_cfg

    latest = pd.read_parquet(APP_DIR / "latest.parquet")
    seen = {}
    for code in latest["code"]:
        cfg = current_cfg(code)
        seen.setdefault((cfg.get("method"), bool(cfg.get("measure"))), code)
    return list(seen.values())


def test_opening_threshold_forms_does_not_save(save_calls):
    """Mở form không được tự lưu (lỗi cũ: N năm gộp từ mặc định làm form lưu lặp vô hạn)."""
    for code in _sample_codes():
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
        at.session_state["is_admin"] = True
        at.session_state["detail_code"] = code
        at.run()
        at.switch_page("app_pages/detail.py").run()
        assert not at.exception, (code, [e.value for e in at.exception])
    assert save_calls == []


def _config_app(**state) -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.session_state["is_admin"] = True
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    at.switch_page("app_pages/scorecard_config.py").run()
    return at


def test_opening_scorecard_rows_does_not_save(save_calls):
    """Mở mọi bộ, mọi phân khúc, mọi dòng ở trang cấu hình: không ghi file, không sinh nháp."""
    from macro_app.profiles import load_profiles

    for pslug, prof in load_profiles().items():
        for slug, card in prof["segments"].items():
            for row in card["rows"]:
                at = _config_app(
                    cfg_profile=pslug,
                    **{f"cfg_seg_{pslug}": slug, f"cfg_pick_{pslug}_{slug}": row["code"]},
                )
                assert not at.exception, (pslug, slug, row["code"], [e.value for e in at.exception])
                assert not at.session_state["sc_drafts"], (pslug, slug, row["code"])
                assert not at.error, (row["code"], [e.value for e in at.error])
    assert save_calls == []


def test_add_segment_goes_to_draft_then_save_writes(save_calls):
    at = _config_app(cfg_profile="theo_doi_bds_01")
    at.text_input(key="cfg_new_seg_name").input("Văn phòng").run()
    at.button(key="cfg_new_seg").click().run()
    assert not at.exception, [e.value for e in at.exception]
    draft = at.session_state["sc_drafts"]["theo_doi_bds_01"]
    assert "Văn phòng" in [c["name"] for c in draft["segments"].values()]
    assert save_calls == []  # chưa bấm Lưu thì chưa ghi
    at.button(key="cfg_save").click().run()
    assert save_calls == [("write_profile", ("theo_doi_bds_01",))]


def test_edit_cuts_updates_draft_only(save_calls):
    p, s, code = "theo_doi_bds_01", "nha_o", "cpi_yoy"
    at = _config_app(cfg_profile=p, **{f"cfg_seg_{p}": s, f"cfg_pick_{p}_{s}": code})
    key = f"cfg_rule_{p}_{s}_{code}_0_cuts"
    at.text_input(key=key).input("2; 3; 4; 5").run()
    assert not at.exception, [e.value for e in at.exception]
    row = next(
        r for r in at.session_state["sc_drafts"][p]["segments"][s]["rows"] if r["code"] == code
    )
    assert row["cuts"] == [2.0, 3.0, 4.0, 5.0]
    assert row["pillar"] == "Ổn định vĩ mô"  # giữ trụ cột
    assert save_calls == []
    at.text_input(key=key).input("2; 3; x").run()  # nhập sai → báo lỗi, nháp giữ nguyên
    assert at.error
    row = next(
        r for r in at.session_state["sc_drafts"][p]["segments"][s]["rows"] if r["code"] == code
    )
    assert row["cuts"] == [2.0, 3.0, 4.0, 5.0]


def test_public_scorecard_csv_hides_vendor_values():
    """Số đã đo / diễn giải của dòng Yahoo, LME không được ra data/public."""
    from macro_app.paths import PUBLIC_DIR

    path = PUBLIC_DIR / "scorecard_rows.csv"
    if not path.exists():
        pytest.skip("chưa build")
    rows = pd.read_csv(path)
    vendor = rows[rows["code"].isin(["dxy", "copper", "brent_futures", "copper_comex"])]
    assert not vendor.empty
    assert vendor["measured"].isna().all()
    assert vendor["detail"].fillna("").eq("").all()


def test_forecast_page_admin_save(monkeypatch):
    """Trang Kế hoạch & dự báo: quản trị thấy bảng sửa; Lưu ghi đúng số dòng."""
    from macro_app import admin

    saved = []
    monkeypatch.setattr(admin, "save_forecast_map", lambda maps, *a, **k: saved.append(maps))
    at = run_page("forecasts", admin=True)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    at.button(key="fmap_save").click().run()
    assert saved and len(saved[0]) == len(
        __import__("macro_app.metrics.forward", fromlist=["x"]).load_forecast_map()
    )


def test_vendor_switch(monkeypatch):
    """Bản deploy ẩn số Yahoo/LME; bật SHOW_VENDOR_DATA=1 thì hiện; local quản trị luôn hiện."""
    from macro_app.ui import data

    monkeypatch.setattr(
        data, "_setting", lambda name: {"APP_MODE": "", "SHOW_VENDOR_DATA": ""}[name]
    )
    assert data.hide_vendor()
    monkeypatch.setattr(
        data, "_setting", lambda name: {"APP_MODE": "", "SHOW_VENDOR_DATA": "1"}[name]
    )
    assert not data.hide_vendor()
    monkeypatch.setattr(
        data, "_setting", lambda name: {"APP_MODE": "admin", "SHOW_VENDOR_DATA": ""}[name]
    )
    assert not data.hide_vendor()
