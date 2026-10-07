"""Chỉ số nhập tay: đọc data/raw/manual/manual_inputs.csv.

App không có form nhập — sửa file CSV trực tiếp.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from macro_app.paths import MANUAL_INPUTS_FILE

COLUMNS = [
    "code",
    "date",
    "value",
    "unit",
    "source",
    "source_url",
    "note",
    "entered_by",
    "entered_at",
    "method",
]


def read_manual(path: Path = MANUAL_INPUTS_FILE) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path, dtype={"code": str}, keep_default_na=False, na_values=[""])
