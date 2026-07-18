"""Repair/export BO7 TTK attachment CSV safely.

Usage:
    python scripts/repair_ttk_attachments.py
    python scripts/repair_ttk_attachments.py --apply

Default mode writes a preview file and report into data/bo7_ttk without
overwriting attachments.csv. Use --apply only after checking the report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from modules.warzone.ttk_csv_repair import write_clean_attachments_csv


DEFAULT_SOURCE = Path("data/bo7_ttk/attachments.csv")
DEFAULT_PREVIEW_OUTPUT = Path("data/bo7_ttk/attachments.repaired.preview.csv")
DEFAULT_REPORT = Path("data/bo7_ttk/attachments.repaired.report.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_PREVIEW_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Back up attachments.csv and replace it with the repaired output.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    report = write_clean_attachments_csv(args.source, args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    print(f"Wrote repaired preview: {args.output}")
    print(f"Wrote report: {args.report}")
    print(f"Dropped malformed rows: {len(report.dropped_malformed_rows)}")
    print(f"Blocked conversion rows: {len(report.blocked_conversion_rows)}")
    print(f"Added conflict rows: {len(report.added_conflict_rows)}")

    if not args.apply:
        print("Dry run only. Re-run with --apply to replace attachments.csv after checking the preview.")
        return

    backup = args.source.with_suffix(".backup.csv")
    shutil.copy2(args.source, backup)
    shutil.copy2(args.output, args.source)
    print(f"Backed up original to: {backup}")
    print(f"Applied repaired CSV to: {args.source}")


if __name__ == "__main__":
    main()
