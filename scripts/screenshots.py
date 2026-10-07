"""Chụp màn hình toàn bộ trang bằng Playwright (yêu cầu nghiệm thu mục 13).

Chạy app trước:  ADMIN_PASSWORD=... streamlit run app.py --server.port 8517
Rồi:             python scripts/screenshots.py --port 8517 [--password ...]
Ảnh lưu ở docs/screenshots/.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
PAGES = {  # trang công khai (nhóm Theo dõi); trang Cấu hình chụp ở nhánh --password
    "1_scorecard": "",
    "2_tong_quan": "overview",
    "3_ke_hoach_du_bao": "forecasts",
    "4_quoc_te": "international",
    "5_viet_nam": "vietnam",
    "8_chi_tiet": "detail",
}
SIZES = {"1440": (1440, 900), "1920": (1920, 1080)}


def wait_ready(page: Page) -> None:
    page.wait_for_selector('[data-testid="stApp"]', timeout=60_000)
    page.wait_for_function(
        "!document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=120_000
    )
    page.mouse.wheel(0, 20000)  # cuộn hết trang để chart nằm dưới cũng được vẽ
    page.wait_for_timeout(1500)
    page.wait_for_function(
        "document.querySelectorAll('[data-testid=\"stPlotlyChart\"]').length * 2 <="
        " document.querySelectorAll('.js-plotly-plot .main-svg').length",
        timeout=60_000,
    )
    page.mouse.wheel(0, -20000)
    page.wait_for_timeout(1500)


def shoot(page: Page, url: str, name: str) -> None:
    page.goto(url)
    wait_ready(page)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    print("saved", name)


def login(page: Page, base: str, password: str) -> None:
    page.goto(base)
    wait_ready(page)
    page.get_by_text("Đăng nhập quản trị").click()
    page.get_by_label("Tên (ghi vào lịch sử)").fill("UAT")
    page.get_by_label("Mật khẩu").fill(password)
    page.get_by_role("button", name="Đăng nhập").click()
    wait_ready(page)


def click_nav(page: Page, title: str, name: str) -> None:
    page.get_by_role("link", name=title).first.click()
    wait_ready(page)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    print("saved", name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8517)
    ap.add_argument("--password", default="")
    args = ap.parse_args()
    base = f"http://localhost:{args.port}/"
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for size, (w, h) in SIZES.items():
            page = browser.new_page(viewport={"width": w, "height": h})
            for name, path in PAGES.items():
                if size == "1920" and name not in ("1_tong_quan", "2_quoc_te"):
                    continue
                shoot(page, base + path, f"{name}_{size}")
            page.close()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(base + "?present=1")
        wait_ready(page)
        page.screenshot(path=str(OUT / "1_tong_quan_trinh_bay_1920x1080.png"), full_page=False)
        page.screenshot(path=str(OUT / "1_tong_quan_trinh_bay_full.png"), full_page=True)
        print("saved presentation")
        page.goto(base + "international")
        wait_ready(page)
        page.locator("[role=tab]", has_text="FedWatch").click()
        page.wait_for_timeout(2500)
        page.screenshot(path=str(OUT / "2_quoc_te_fedwatch_1440.png"), full_page=True)
        page.close()
        if args.password:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            login(page, base, args.password)
            click_nav(page, "Ngưỡng", "5_nguong_quan_tri")
            click_nav(page, "Cấu hình scorecard", "4b_cau_hinh_scorecard")
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
