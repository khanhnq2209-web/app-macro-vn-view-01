"""Đường dẫn dùng chung — mọi module import từ đây, không tự ghép đường dẫn."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
MANUAL_DIR = RAW_DIR / "manual"
INBOX_DIR = DATA_DIR / "inbox"
BACKUP_DIR = RAW_DIR / "_backup"
CACHE_DIR = DATA_DIR / "cache"
PUBLIC_DIR = DATA_DIR / "public"
APP_DIR = DATA_DIR / "app"  # store nội bộ cho app (gồm cả chuỗi Yahoo)

DEPOSIT_FILE = RAW_DIR / "01_deposit rate.xlsx"
BANKS_FILE = RAW_DIR / "03_tctd.xlsx"
MANUAL_INPUTS_FILE = MANUAL_DIR / "manual_inputs.csv"
