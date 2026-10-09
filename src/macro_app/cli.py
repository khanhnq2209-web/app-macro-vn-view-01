"""CLI: python -m macro_app.cli build | refresh [--sources fred,yahoo,...] | merge-inbox

Chạy từ gốc repo với PYTHONPATH=src (hoặc `pip install -e .`).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from dotenv import load_dotenv

from macro_app import admin
from macro_app.build import run_build
from macro_app.paths import ROOT

ALL_SOURCES = ["fred", "yahoo", "fedwatch", "simplize", "vbma", "lme", "gpr"]


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252
    load_dotenv(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="macro_app")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="Tính lại data/app + data/public từ raw + cache")
    p_refresh = sub.add_parser("refresh", help="Tải lại nguồn rồi build")
    p_refresh.add_argument("--sources", default=",".join(ALL_SOURCES))
    sub.add_parser("merge-inbox", help="Gộp file Excel trong data/inbox vào data/raw rồi build")
    args = parser.parse_args(argv)

    if args.cmd == "refresh":
        names = [s.strip() for s in args.sources.split(",") if s.strip()]
        results = admin.refresh_sources(names)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.cmd == "merge-inbox":
        report = admin.merge_inbox()
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    meta = run_build()
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0 if not meta["source_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
