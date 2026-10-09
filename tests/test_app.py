"""AppTest: mọi trang chạy không lỗi; Tổng quan khớp latest; chế độ công khai không có nút ghi."""

import json
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
    admin = page in ("scorecard_config", "views_editor")  # nhóm Cấu hình
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


def test_data_pages_have_no_threshold_status():
    """Các trang Theo dõi (trừ Scorecard) chỉ xem số: không còn chấm màu/trạng thái ngưỡng."""
    at = run_page("overview")
    html = " ".join(h.proto.body for h in at.get("html"))
    assert "Đổi màu" not in html and "ms-dot" not in html and "mv-dot" not in html
    detail = run_page("detail")
    assert "Trạng thái ngưỡng" not in [m.label for m in detail.metric]
    assert not [e for e in detail.expander if "Ngưỡng" in e.label]


@pytest.fixture
def save_calls(monkeypatch):
    """Ghi lại mọi lần lưu (ngưỡng, bộ cấu hình) thay vì ghi file thật."""
    from macro_app import admin, build, profiles
    from macro_app.ui import threshold_form

    calls = []
    for mod, name in (
        (admin, "save_threshold"),
        (profiles, "write_profile"),
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


def test_detail_page_does_not_save(save_calls):
    """Mở trang Chi tiết với mọi kiểu chỉ số: chạy được và không ghi gì."""
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
    at.session_state["admin_name"] = "test"
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    at.switch_page("app_pages/scorecard_config.py").run()
    return at


def _store_rows() -> list[dict]:
    from macro_app.ui import profile_store

    return profile_store.store().rows()


def _ok(at: AppTest) -> None:
    assert not at.exception, [e.value for e in at.exception]


def test_config_page_needs_password(monkeypatch):
    """Không phải quản trị: phải nhập CONFIG_PASSWORD; sai 5 lần thì khóa."""
    from macro_app.ui import sidebar

    monkeypatch.setattr(sidebar, "secret", lambda n: "mk-dung" if n == "CONFIG_PASSWORD" else "")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.session_state["is_admin"] = False
    at.run()
    at.switch_page("app_pages/scorecard_config.py").run()
    _ok(at)
    assert not [b for b in at.button if b.key == "cfg_new_btn"]  # chưa mở khóa
    for _ in range(5):
        at.text_input(key="gate_name").input("Lan")
        at.text_input(key="gate_pw").input("sai")
        next(b for b in at.button if b.label == "Mở khóa").click().run()
    at.run()  # lần tải sau lần sai thứ 5: bị khóa, không còn form
    assert any("Thử lại sau" in e.value for e in at.error)
    assert not [b for b in at.button if b.label == "Mở khóa"]
    from macro_app.ui import editor_gate

    fresh = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)  # phiên mới vẫn bị khóa
    fresh.session_state["is_admin"] = False
    fresh.run()
    fresh.switch_page("app_pages/scorecard_config.py").run()
    assert any("Thử lại sau" in e.value for e in fresh.error)
    editor_gate.reset_counters()
    at.run()
    at.text_input(key="gate_name").input("Lan")
    at.text_input(key="gate_pw").input("mk-dung")
    next(b for b in at.button if b.label == "Mở khóa").click().run()
    _ok(at)
    assert at.session_state["editor_name"] == "Lan"
    assert [b for b in at.button if b.key == "cfg_new_btn"]


def _open(at: AppTest, profile: str, segment: str, step: int, code: str | None = None) -> AppTest:
    at.session_state["cfg_target"] = {
        "profile": profile,
        "segment": segment,
        "step": step,
        "code": code,
    }
    at.run()
    return at


def test_opening_every_row_does_not_change_draft_or_save():
    """Mở mọi bộ, phân khúc, dòng ở bước 3: không lỗi, bản nháp không đổi, không ghi kho."""
    from macro_app.profiles import is_dirty, load_profiles

    at = _config_app()
    for pslug, prof in load_profiles().items():
        for slug, card in prof["segments"].items():
            for row in card["rows"]:
                _open(at, pslug, slug, 3, row["code"])
                _ok(at)
                assert not at.error, (row["code"], [e.value for e in at.error])
                assert not is_dirty(at.session_state["cfg_draft"], prof), row["code"]
    for step in (1, 2, 4):
        _open(at, "theo_doi_bds_01", "nha_o", step)
        _ok(at)
    assert _store_rows() == []


def _cut_key(at: AppTest, seg: str, code: str, i: int) -> str:
    v = at.session_state["cfg_ver"]
    return f"cfg_rule_{seg}_{code}_{v}_cut5_{i}"


def test_edit_cut_then_save_writes_one_version():
    at = _config_app()
    _open(at, "theo_doi_bds_01", "nha_o", 3, "cpi_yoy")
    at.number_input(key=_cut_key(at, "nha_o", "cpi_yoy", 2)).set_value(4.7).run()
    _ok(at)
    row = next(
        r
        for r in at.session_state["cfg_draft"]["segments"]["nha_o"]["rows"]
        if r["code"] == "cpi_yoy"
    )
    assert row["cuts"][2] == 4.7 and row["pillar"] == "Ổn định vĩ mô"
    assert _store_rows() == []  # chưa bấm Lưu
    at.button(key="cfg_save").click().run()
    _ok(at)
    rows = _store_rows()
    assert len(rows) == 1 and rows[0]["bo_id"] == "theo_doi_bds_01"
    assert rows[0]["saved_by"] == "test" and int(rows[0]["version"]) == 1
    saved = json.loads(rows[0]["payload"])
    cpi = next(r for r in saved["segments"]["nha_o"]["rows"] if r["code"] == "cpi_yoy")
    assert cpi["cuts"][2] == 4.7


def test_cuts_not_increasing_show_error_and_keep_draft():
    at = _config_app()
    _open(at, "theo_doi_bds_01", "nha_o", 3, "cpi_yoy")
    at.number_input(key=_cut_key(at, "nha_o", "cpi_yoy", 2)).set_value(1.0).run()
    _ok(at)
    assert any("tăng dần" in e.value for e in at.error)
    row = next(
        r
        for r in at.session_state["cfg_draft"]["segments"]["nha_o"]["rows"]
        if r["code"] == "cpi_yoy"
    )
    assert row["cuts"] == [2.5, 3.5, 4.5, 5.5]


def test_save_conflict_keeps_draft_and_does_not_overwrite():
    from macro_app import config_store as cs
    from macro_app.profiles import load_profiles
    from macro_app.ui import profile_store

    at = _config_app()
    _open(at, "theo_doi_bds_01", "nha_o", 3, "cpi_yoy")
    at.number_input(key=_cut_key(at, "nha_o", "cpi_yoy", 2)).set_value(4.6).run()
    other = load_profiles()["theo_doi_bds_01"]
    cs.save(profile_store.store(), "theo_doi_bds_01", other, base=0, by="Người khác")
    at.button(key="cfg_save").click().run()
    _ok(at)
    assert "người khác" in at.session_state["cfg_conflict"]
    assert len(_store_rows()) == 1  # không ghi đè


def test_new_scorecard_from_blank():
    at = _config_app()
    at.button(key="cfg_new_btn").click().run()
    v = at.session_state["cfg_ver"]
    at.text_input(key=f"cfg_name_{v}").input("Theo dõi KCN · 02").run()
    at.button(key="cfg_step_btn_2").click().run()
    seg = at.session_state["cfg_seg"]
    v = at.session_state["cfg_ver"]
    at.text_input(key=f"cfg_gnew_{seg}_{v}").input("Sản xuất").run()
    at.button(key=f"cfg_gadd_{seg}_{v}").click().run()
    v = at.session_state["cfg_ver"]
    at.selectbox(key=f"cfg_radd_{seg}_0_{v}").set_value("pmi_vn").run()
    at.button(key=f"cfg_raddbtn_{seg}_0_{v}").click().run()
    _ok(at)
    assert at.session_state["cfg_unconf"] == [f"{seg}/pmi_vn"]
    assert at.button(key="cfg_save").disabled  # chưa xác nhận mốc
    at.button(key="cfg_step_btn_3").click().run()
    at.button(key=f"cfg_conf_{seg}_pmi_vn").click().run()
    _ok(at)
    assert not at.button(key="cfg_save").disabled
    at.button(key="cfg_save").click().run()
    _ok(at)
    rows = _store_rows()
    assert [r["bo_id"] for r in rows] == ["theo_doi_kcn_02"]
    body = json.loads(rows[0]["payload"])
    assert body["segments"][seg]["pillars"] == [{"name": "Sản xuất"}]


def test_add_segment_copied_from_existing():
    at = _config_app()
    _open(at, "theo_doi_bds_01", "nha_o", 1)
    v = at.session_state["cfg_ver"]
    at.text_input(key=f"cfg_segnew_{v}").input("Văn phòng")
    at.selectbox(key=f"cfg_segsrc_{v}").set_value("theo_doi_bds_01/nha_o").run()
    at.button(key=f"cfg_segadd_{v}").click().run()
    _ok(at)
    segs = at.session_state["cfg_draft"]["segments"]
    new = next(c for c in segs.values() if c["name"] == "Văn phòng")
    assert len(new["rows"]) == len(segs["nha_o"]["rows"])
    assert _store_rows() == []  # chưa lưu


def test_group_weight_override_changes_draft_weights():
    at = _config_app()
    _open(at, "theo_doi_bds_01", "nha_o", 2)
    v = at.session_state["cfg_ver"]
    at.number_input(key=f"cfg_gw_nha_o_2_{v}").set_value(40.0).run()  # Cầu và thu nhập
    _ok(at)
    pillars = at.session_state["cfg_draft"]["segments"]["nha_o"]["pillars"]
    assert {"name": "Cầu và thu nhập", "weight": 40.0} in pillars
    assert not at.button(key="cfg_save").disabled  # 40% + 4 nhóm tự chia 15% = 100%


def test_scorecard_page_v3_blocks_and_edit_shortcut():
    at = run_page("scorecard")
    _ok(at)
    html = " ".join(h.proto.body for h in at.get("html"))
    for text in ("Vì sao điểm thế này", "Độ tin cậy", "Tổng đóng góp = điểm tổng", "Thông tin"):
        assert text in html, text
    assert "Trọng số thực dùng" not in html  # ẩn mặc định
    at.toggle(key="sc_show_w").set_value(True).run()
    html = " ".join(h.proto.body for h in at.get("html"))
    assert "Trọng số thực dùng" in html
    at.session_state["is_admin"] = True
    at.button(key="sc_edit_groups").click().run()
    _ok(at)
    assert at.session_state["cfg_step"] == 2 and at.session_state["cfg_view"] == "wiz"


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


def test_scorecard_report_buttons():
    at = run_page("scorecard")
    at.button(key="sc_make_report").click().run()
    _ok(at)
    assert at.session_state["sc_report_for"][2] == 1
