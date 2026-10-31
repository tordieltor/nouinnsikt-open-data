#!/usr/bin/env python3
"""
Quickstart examples for querying the NOUinnsikt Open Raw-Data Archive
using only Python's standard library (plus optional NumPy / SQLite FTS5).
"""

import csv
import gzip
import json
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REL_DIR = REPO_ROOT / "datasets" / "relational"
CAT_DIR = REPO_ROOT / "datasets" / "catalogs"


def main() -> None:
    # 1. Load flat NOU catalog CSV (1,741 official NOUs)
    with (REL_DIR / "nous_flat.csv").open(encoding="utf-8") as f:
        nous = list(csv.DictReader(f))
    nynorsk_count = sum(1 for r in nous if r["is_nynorsk"] == "true")
    print(f"Total NOUs: {len(nous):,} (Nynorsk: {nynorsk_count:,}, Bokmål: {len(nous) - nynorsk_count:,})")

    # 2. Top 5 most frequently appointed committee chairs (1972-2026)
    with (REL_DIR / "nou_authors.csv").open(encoding="utf-8") as f:
        chairs = [r["name"] for r in csv.DictReader(f) if r["role"] == "leader"]
    print("\nTop 5 Committee Chairs (1972-2026):")
    for name, count in Counter(chairs).most_common(5):
        print(f"  {name}: {count} commissions chaired")

    # 3. Inspect full JSONL object from nous.jsonl.gz
    with gzip.open(REL_DIR / "nous.jsonl.gz", "rt", encoding="utf-8") as gz:
        sample = json.loads(next(gz))
    print(f"\nSample full NOU record: {sample['title']} (ID: {sample['id']})")

    # 4. Inspect minority dissents catalog
    dissents = json.loads((CAT_DIR / "dissent_catalog.json").read_text(encoding="utf-8"))
    total_dissents = len(dissents.get("items", [])) if isinstance(dissents, dict) else len(dissents)
    print(f"Verified minority dissents loaded: {total_dissents:,}")


if __name__ == "__main__":
    main()
