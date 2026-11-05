"""
Recipient Ministry Extraction and Lineage Backfill Pipeline
------------------------------------------------------------
Sweeps opening chunks (0–30) across all 1,741 NOUs in Supabase PostgreSQL
to extract authentic historical recipient ministries from transmittal letters
(overleveringsbrev) and mandate appointment records, attaching both the authentic
historical ministry name and canonical modern lineage to public.nous.document_profile.
"""

import os
import sys
import json
import re
import argparse
import time
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Optional, Any

# Ensure backend and root are in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.lib.db import get_db
from app.lib.ministry_resolver import (
    resolve_ministry_lineage,
    normalize_ministry_name,
    load_ministry_lineage,
    get_all_historical_ministries
)

# Build regex pattern for all known historical names from lineage JSON
def _build_regex_patterns():
    lineage_data = load_ministry_lineage()
    historical_map = lineage_data.get("historical_to_modern_map", {})

    dept_variants = []
    for name in sorted(historical_map.keys(), key=len, reverse=True):
        pattern = re.escape(name)
        pattern = pattern.replace(r'\-', r'[\-\–\—\s]+')
        pattern = pattern.replace(r'\ ', r'\s+')
        if pattern.endswith('departementet'):
            base = pattern[:-2]
            pattern = f"{base}(?:et)?"
        dept_variants.append(pattern)

    dept_group = '|'.join(dept_variants)

    # 1. Primary transmittal address triggers
    transmittal_triggers = [
        r'Til\s+(?:det\s+[Kk]ongelige\s+|det\s+kgl\.\s+|[Ss]tatsråd(?:en)?\s+(?:[A-ZÆØÅ][a-zæøå]+\s+)*i\s+)?',
        r'Avgitt\s+til\s+(?:det\s+[Kk]ongelige\s+|det\s+kgl\.\s+|[Ss]tatsråd(?:en)?\s+(?:[A-ZÆØÅ][a-zæøå]+\s+)*i\s+)?',
        r'Overlevert\s+(?:til\s+)?(?:det\s+[Kk]ongelige\s+|det\s+kgl\.\s+|[Ss]tatsråd(?:en)?\s+(?:[A-ZÆØÅ][a-zæøå]+\s+)*i\s+)?',
        r'Fremmet\s+for\s+(?:det\s+[Kk]ongelige\s+|det\s+kgl\.\s+|[Ss]tatsråd(?:en)?\s+(?:[A-ZÆØÅ][a-zæøå]+\s+)*i\s+)?',
        r'Sendt\s+(?:til\s+)?(?:det\s+[Kk]ongelige\s+|det\s+kgl\.\s+|[Ss]tatsråd(?:en)?\s+(?:[A-ZÆØÅ][a-zæøå]+\s+)*i\s+)?',
        r'(?:legges|overleveres|avgis)\s+herved\s+(?:til|for)\s+(?:det\s+[Kk]ongelige\s+|det\s+kgl\.\s+|[Ss]tatsråd(?:en)?\s+(?:[A-ZÆØÅ][a-zæøå]+\s+)*i\s+)?',
        r'(?:Avgitt|Overlevert)\s+den\s+\d{1,2}\.\s+[a-zæøå]+\s+\d{4}\s+til\s+(?:det\s+[Kk]ongelige\s+|det\s+kgl\.\s+|[Ss]tatsråd(?:en)?\s+(?:[A-ZÆØÅ][a-zæøå]+\s+)*i\s+)?'
    ]

    transmittal_re = re.compile(
        r'(?:' + '|'.join(transmittal_triggers) + r')(' + dept_group + r')',
        re.IGNORECASE
    )

    # 2. Secondary fallback (mandate / appointment clause)
    fallback_re = re.compile(
        r'(?:oppnevnt\s+(?:ved\s+kongelig\s+resolusjon\s+fra|av|i)|utredning\s+fra\s+utvalg\s+oppnevnt\s+av)\s+'
        r'(?:[Dd]et\s+[Kk]ongelige\s+|[Dd]et\s+kgl\.\s+)?'
        r'(' + dept_group + r')',
        re.IGNORECASE
    )

    return transmittal_re, fallback_re

TRANSMITTAL_RE, FALLBACK_RE = _build_regex_patterns()

# Compatibility aliases
MINISTRY_LINEAGE_MAP = load_ministry_lineage().get("historical_to_modern_map", {})
COMPILED_DEPT_PATTERN = TRANSMITTAL_RE
clean_department_name = normalize_ministry_name


def extract_recipient_from_chunks(chunks: List[Tuple[int, str]]) -> Tuple[Optional[str], Optional[str]]:
    """
    Scans sequential chunks and extracts recipient ministry.
    Returns: (historical_name, match_source)
    """
    # Pass 1: Primary transmittal address pattern
    for chunk_index, content in chunks:
        if not content:
            continue
        m = TRANSMITTAL_RE.search(content)
        if m:
            raw_dept = m.group(1)
            norm_dept = normalize_ministry_name(raw_dept)
            resolved = resolve_ministry_lineage(norm_dept)
            if resolved.get("is_known"):
                return resolved["historical_name"], f"transmittal_chunk_{chunk_index}"

    # Pass 2: Secondary mandate / appointment pattern
    for chunk_index, content in chunks:
        if not content:
            continue
        m = FALLBACK_RE.search(content)
        if m:
            raw_dept = m.group(1)
            norm_dept = normalize_ministry_name(raw_dept)
            resolved = resolve_ministry_lineage(norm_dept)
            if resolved.get("is_known"):
                return resolved["historical_name"], f"appointment_chunk_{chunk_index}"

    return None, None


def run_pipeline(dry_run: bool = True, max_chunk: int = 30, batch_size: int = 100) -> Dict[str, Any]:
    print("=" * 70)
    print("  NOUINNS IKT — RECIPIENT MINISTRIES & LINEAGE BACKFILL PIPELINE")
    print("=" * 70)
    print(f"Mode:            {'DRY RUN (Read-Only Audit)' if dry_run else 'APPLY (Mutating Database Update)'}")
    print(f"Max Chunk Depth: Chunks 0–{max_chunk}")
    print(f"Batch Size:      {batch_size}")
    print(f"Timestamp:       {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 70)

    start_time = time.time()

    with get_db() as cur:
        print("[1/4] Fetching all NOUs from Supabase public.nous...")
        cur.execute("SELECT id, title, year, document_profile FROM nous ORDER BY year ASC, id ASC;")
        nous = cur.fetchall()
        total_nous = len(nous)
        print(f"      Loaded {total_nous} NOUs.")

        print(f"[2/4] Fetching opening text chunks (chunk_index <= {max_chunk}) from public.nou_chunks...")
        cur.execute("""
            SELECT nou_id, chunk_index, content
            FROM nou_chunks
            WHERE chunk_index <= %s
            ORDER BY nou_id ASC, chunk_index ASC;
        """, (max_chunk,))
        all_chunks = cur.fetchall()
        print(f"      Loaded {len(all_chunks)} text chunks.")

    # Group chunks by nou_id
    chunks_by_nou = defaultdict(list)
    for c in all_chunks:
        chunks_by_nou[str(c["nou_id"])].append((c["chunk_index"], c["content"]))

    print("[3/4] Running extraction and ministerial lineage mapping...")
    
    baseline_has_mottaker = 0
    newly_extracted = 0
    total_post_coverage = 0
    
    decade_before = defaultdict(lambda: {"total": 0, "has": 0})
    decade_after = defaultdict(lambda: {"total": 0, "has": 0})
    
    historical_dist = Counter()
    lineage_dist = Counter()
    updates_to_execute = []

    for row in nous:
        nid = str(row["id"])
        year = row.get("year") or 2000
        decade_str = f"{(year // 10) * 10}-talet"
        
        decade_before[decade_str]["total"] += 1
        decade_after[decade_str]["total"] += 1

        prof = row.get("document_profile") or {}
        if isinstance(prof, str):
            try:
                prof = json.loads(prof)
            except Exception:
                prof = {}
        elif not isinstance(prof, dict):
            prof = {}

        existing_m = prof.get("mottaker")
        has_valid_existing = bool(
            existing_m and isinstance(existing_m, str) and len(existing_m.strip()) > 3 and existing_m.strip() != "Departementet"
        )
        if has_valid_existing:
            baseline_has_mottaker += 1
            decade_before[decade_str]["has"] += 1

        # Extract from text chunks
        chunks = chunks_by_nou.get(nid, [])
        extracted_dept, match_src = extract_recipient_from_chunks(chunks)

        chosen_dept = None
        if extracted_dept:
            chosen_dept = extracted_dept
        elif has_valid_existing:
            # Normalize existing
            norm_ex = normalize_ministry_name(existing_m)
            res_ex = resolve_ministry_lineage(norm_ex)
            if res_ex.get("is_known"):
                chosen_dept = res_ex["historical_name"]
            else:
                chosen_dept = norm_ex

        if chosen_dept:
            resolved = resolve_ministry_lineage(chosen_dept)
            canonical = resolved.get("canonical_name", chosen_dept)
            code = resolved.get("code")

            historical_dist[chosen_dept] += 1
            lineage_dist[canonical] += 1
            total_post_coverage += 1
            decade_after[decade_str]["has"] += 1

            if not has_valid_existing:
                newly_extracted += 1

            # Prepare document_profile update
            updated_prof = dict(prof)
            updated_prof["mottaker"] = chosen_dept
            updated_prof["mottaker_lineage"] = canonical
            if code:
                updated_prof["mottaker_code"] = code

            updates_to_execute.append((nid, json.dumps(updated_prof, ensure_ascii=False)))

    print(f"      Extraction complete in {time.time() - start_time:.2f}s.")
    print("\n" + "=" * 70)
    print("  EXTRACTION & COVERAGE SUMMARY")
    print("=" * 70)
    print(f"Total Corpus NOUs:            {total_nous}")
    print(f"Baseline Mottaker Coverage:    {baseline_has_mottaker} / {total_nous} ({baseline_has_mottaker / total_nous * 100:.1f}%)")
    print(f"Newly Extracted NOUs:         +{newly_extracted}")
    print(f"Total Post-Sweep Coverage:    {total_post_coverage} / {total_nous} ({total_post_coverage / total_nous * 100:.1f}%)")
    print(f"Net Coverage Expansion:       +{total_post_coverage - baseline_has_mottaker} NOUs (+{(total_post_coverage - baseline_has_mottaker) / total_nous * 100:.1f} pp)")
    print(f"Pending Database Updates:     {len(updates_to_execute)} NOUs")
    print("-" * 70)

    print("\n--- COVERAGE BY DECADE (BASELINE -> POST-SWEEP) ---")
    for dec in sorted(decade_before.keys()):
        b_has = decade_before[dec]["has"]
        b_tot = decade_before[dec]["total"]
        b_pct = (b_has / b_tot) * 100 if b_tot else 0

        a_has = decade_after[dec]["has"]
        a_tot = decade_after[dec]["total"]
        a_pct = (a_has / a_tot) * 100 if a_tot else 0
        gain = a_has - b_has
        print(f"  {dec:10s}: {b_has:3d}/{b_tot:3d} ({b_pct:5.1f}%)  -->  {a_has:3d}/{a_tot:3d} ({a_pct:5.1f}%)  [+{gain:3d}]")

    print("\n--- TOP 12 HISTORICAL MINISTRIES EXTRACTED ---")
    for name, cnt in historical_dist.most_common(12):
        print(f"  {name:48s}: {cnt:4d} NOUs")

    print("\n--- TOP 12 CONSOLIDATED MODERN LINEAGES ---")
    for name, cnt in lineage_dist.most_common(12):
        print(f"  {name:48s}: {cnt:4d} NOUs")

    if not dry_run:
        print("\n[4/4] Writing batch updates to public.nous in Supabase PostgreSQL...")
        write_start = time.time()
        with get_db() as cur:
            for i in range(0, len(updates_to_execute), batch_size):
                batch = updates_to_execute[i:i + batch_size]
                # Use parameterized update loop
                for nid, prof_json in batch:
                    cur.execute(
                        "UPDATE nous SET document_profile = %s WHERE id = %s;",
                        (prof_json, nid)
                    )
                print(f"      Committed {min(i + batch_size, len(updates_to_execute))}/{len(updates_to_execute)} records...")
        print(f"      All {len(updates_to_execute)} records successfully updated in {time.time() - write_start:.2f}s!")
    else:
        print("\n[4/4] DRY RUN MODE: No changes written to database.")
        print("      To apply updates, run with `--apply`.")

    return {
        "total_nous": total_nous,
        "baseline_coverage": baseline_has_mottaker,
        "newly_extracted": newly_extracted,
        "total_post_coverage": total_post_coverage,
        "coverage_pct": (total_post_coverage / total_nous) * 100 if total_nous else 0,
        "historical_distribution": dict(historical_dist),
        "lineage_distribution": dict(lineage_dist),
        "updates_count": len(updates_to_execute)
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recipient Ministry Extraction & Lineage Backfill Pipeline")
    parser.add_argument("--apply", action="store_true", help="Apply updates directly to Supabase PostgreSQL database")
    parser.add_argument("--dry-run", action="store_true", help="Run read-only analysis without updating database (default)")
    parser.add_argument("--max-chunk", type=int, default=30, help="Maximum chunk index to scan (default: 30)")
    parser.add_argument("--batch-size", type=int, default=100, help="Database update batch size (default: 100)")

    args = parser.parse_args()
    is_dry_run = not args.apply

    run_pipeline(dry_run=is_dry_run, max_chunk=args.max_chunk, batch_size=args.batch_size)
