"""Đọc toàn bộ file cấu hình trong config/; module khác không tự mở YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from macro_app.paths import CONFIG_DIR

GROUP_BLOCK = {"A": "external", "B": "domestic", "C": "domestic", "D": "domestic", "E": "domestic"}
REQUIRED_FIELDS = ("code", "name", "group", "unit", "frequency", "source", "recipe", "direction")
VALID_FREQ = {"D", "W", "M", "Q", "A"}
VALID_DIRECTION = {"up_bad", "up_good", "two_way"}


def read_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@dataclass(frozen=True)
class Indicator:
    code: str
    name: str
    group: str
    unit: str
    frequency: str
    source: str
    recipe: dict
    direction: str
    source_url: str = ""
    change_unit: str = "pct"
    segment: str = "both"
    target: str | None = None
    flags: tuple[str, ...] = ()
    representative: bool = False
    decimals: int = 2
    manual: bool = False
    derived: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def block(self) -> str:
        return GROUP_BLOCK[self.group[0]]


def _to_indicator(raw: dict) -> Indicator:
    missing = [f for f in REQUIRED_FIELDS if f not in raw]
    if missing:
        raise ValueError(f"catalog: {raw.get('code', '?')} thiếu trường {missing}")
    if raw["frequency"] not in VALID_FREQ:
        raise ValueError(f"catalog: {raw['code']} frequency không hợp lệ: {raw['frequency']}")
    if raw["direction"] not in VALID_DIRECTION:
        raise ValueError(f"catalog: {raw['code']} direction không hợp lệ: {raw['direction']}")
    known = set(Indicator.__dataclass_fields__) - {"extra", "flags"}
    kwargs = {k: v for k, v in raw.items() if k in known}
    extra = {k: v for k, v in raw.items() if k not in known and k != "flags"}
    return Indicator(**kwargs, flags=tuple(raw.get("flags") or ()), extra=extra)


def load_catalog(config_dir: Path = CONFIG_DIR) -> list[Indicator]:
    data = read_yaml(config_dir / "catalog.yaml")
    indicators = [_to_indicator(item) for item in data["indicators"]]
    codes = [i.code for i in indicators]
    dupes = {c for c in codes if codes.count(c) > 1}
    if dupes:
        raise ValueError(f"catalog: mã trùng {sorted(dupes)}")
    return indicators


def load_targets(config_dir: Path = CONFIG_DIR) -> dict:
    return read_yaml(config_dir / "catalog.yaml").get("targets", {})


def load_thresholds(config_dir: Path = CONFIG_DIR) -> tuple[dict, dict]:
    """Trả (default, overrides theo mã).

    File trong thresholds.d nạp theo tên, file sau đè file trước.
    """
    default = read_yaml(config_dir / "thresholds.default.yaml")["default"]
    overrides: dict[str, dict] = {}
    sets = load_threshold_sets(config_dir)
    for slug in active_threshold_sets(config_dir):  # bộ đang chọn: giữa mặc định và file ghi đè
        for code, cfg in (sets.get(slug, {}).get("items") or {}).items():
            overrides[code] = {**(cfg or {}), "_file": f"bộ: {sets[slug]['name']}"}
    for path in sorted((config_dir / "thresholds.d").glob("*.yaml")):
        for code, cfg in (read_yaml(path) or {}).items():
            overrides[code] = {**(cfg or {}), "_file": path.name}
    return default, overrides


THRESHOLD_SETS = "threshold_sets"
ACTIVE_SET_FILE = "_active.yaml"


def load_threshold_sets(config_dir: Path = CONFIG_DIR) -> dict[str, dict]:
    """Các bộ ngưỡng có tên: {slug: {"name", "description", "items": {mã: cấu hình}}}."""
    folder = config_dir / THRESHOLD_SETS
    if not folder.exists():
        return {}
    out = {}
    for path in sorted(folder.glob("*.yaml")):
        if path.name == ACTIVE_SET_FILE:
            continue
        data = read_yaml(path)
        out[path.stem] = {
            "name": data.get("name") or path.stem,
            "description": data.get("description", ""),
            "items": data.get("items") or {},
        }
    return out


def active_threshold_sets(config_dir: Path = CONFIG_DIR) -> list[str]:
    """Các bộ đang bật, theo thứ tự áp dụng (bộ sau đè bộ trước)."""
    path = config_dir / THRESHOLD_SETS / ACTIVE_SET_FILE
    active = read_yaml(path).get("active") if path.exists() else None
    if not active:
        return []
    return [active] if isinstance(active, str) else list(active)


def load_impact_rules(config_dir: Path = CONFIG_DIR) -> dict:
    return read_yaml(config_dir / "impact_rules.yaml")


def load_app_params(config_dir: Path = CONFIG_DIR) -> dict:
    return read_yaml(config_dir / "app.yaml")


def load_sources(config_dir: Path = CONFIG_DIR) -> dict:
    return read_yaml(config_dir / "sources.yaml")
