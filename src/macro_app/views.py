"""View hiển thị: mẫu mặc định (config/views.yaml) + view dùng chung (config/views.d/*.yaml).

View chỉ đổi cách hiển thị (chỉ số, thứ tự, khối, chart), không chạm công thức/ngưỡng.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from macro_app.paths import CONFIG_DIR

DEFAULT_NAME = "Mặc định"
VIEWS_DIR = CONFIG_DIR / "views.d"
CHART_KEYS = {
    "group",
    "title",
    "codes",
    "kind",
    "range",
    "transform",
    "show_target",
    "show_bands",
    "secondary",
    "note",
}
KINDS = {"line", "bar", "area"}
RANGES = {"1Y", "3Y", "5Y", "10Y", "ALL"}
TRANSFORMS = {"level", "yoy", "ytd", "zscore"}


def load_default(config_dir: Path = CONFIG_DIR) -> dict:
    with (config_dir / "views.yaml").open(encoding="utf-8") as fh:
        view = yaml.safe_load(fh)
    view["name"] = DEFAULT_NAME
    return view


def _slug(name: str) -> str:
    return re.sub(r"[^\w-]+", "_", name).strip("_")[:60] or "view"


def list_shared(views_dir: Path = VIEWS_DIR) -> dict[str, dict]:
    out = {}
    for path in sorted(views_dir.glob("*.yaml")):
        with path.open(encoding="utf-8") as fh:
            view = yaml.safe_load(fh) or {}
        out[view.get("name") or path.stem] = view
    return out


def validate(view: dict, known_codes: set[str]) -> list[str]:
    """Lỗi cấu trúc / mã không có trong catalog."""
    errors = []
    if not view.get("name"):
        errors.append("View thiếu tên")
    for block in (view.get("overview") or {}).get("blocks", []):
        errors += [
            f"Khối '{block.get('title')}': mã lạ {c}"
            for c in block.get("codes", [])
            if c not in known_codes
        ]
    for page in ("international", "vietnam"):
        section = view.get(page) or {}
        for chart in (
            section.get("charts", []) + section.get("derived", []) + section.get("sample", [])
        ):
            errors += _chart_errors(chart, known_codes)
    return errors


def _chart_errors(chart: dict, known: set[str]) -> list[str]:
    title = chart.get("title", "?")
    errors = [f"Chart '{title}': mã lạ {c}" for c in chart.get("codes", []) if c not in known]
    if not chart.get("codes"):
        errors.append(f"Chart '{title}': chưa chọn chỉ số")
    if chart.get("kind", "line") not in KINDS:
        errors.append(f"Chart '{title}': kiểu không hợp lệ")
    if chart.get("range", "5Y") not in RANGES:
        errors.append(f"Chart '{title}': khoảng không hợp lệ")
    if chart.get("transform", "level") not in TRANSFORMS:
        errors.append(f"Chart '{title}': biến đổi không hợp lệ")
    unknown = set(chart) - CHART_KEYS
    if unknown:
        errors.append(f"Chart '{title}': khóa lạ {sorted(unknown)}")
    return errors


def to_yaml(view: dict) -> str:
    return yaml.safe_dump(view, allow_unicode=True, sort_keys=False)


def from_yaml(text: str) -> dict:
    try:
        view = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML không hợp lệ: {exc}") from exc
    if not isinstance(view, dict):
        raise ValueError("Nội dung YAML không phải một view")
    return view


def save_shared(view: dict, views_dir: Path = VIEWS_DIR) -> Path:
    if view.get("name") == DEFAULT_NAME:
        raise ValueError("Không ghi đè được view 'Mặc định' — đặt tên khác")
    views_dir.mkdir(parents=True, exist_ok=True)
    path = views_dir / f"{_slug(view['name'])}.yaml"
    path.write_text(to_yaml(view), encoding="utf-8")
    return path


def delete_shared(name: str, views_dir: Path = VIEWS_DIR) -> None:
    path = views_dir / f"{_slug(name)}.yaml"
    if path.exists():
        path.unlink()
