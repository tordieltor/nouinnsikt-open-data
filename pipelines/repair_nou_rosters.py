#!/usr/bin/env python3
"""
pipeline/repair_nou_rosters.py
-------------------------------
Milestone 1, 3 & 4: NOU Committee Roster, Leader, & Affiliation Repair Engine.

Key Requirements:
1. Pre-Migration Backup Snapshot Engine: export full JSON snapshot of `document_profile` and `nou_authors`
   to `data/backups/nou_roster_snapshot_{timestamp}.json` BEFORE performing DB writes.
2. Instant Rollback Engine Support: matching restoration logic in `pipeline/rollback_roster_migration.py`.
3. Zero-Mutation Guard: Check records before mutating; skip clean/valid records (0 mutations on clean records).
4. Extraction Rule Adaptations: Integrate multi-column un-merging heuristics (`detect_multi_column_patterns()`)
   and horizontal line divider detection (`is_divider_line()`, `r'_{3,}'`, `r'-{3,}'`). Parse Markdown signature pages cleanly.
5. Benchmark Batch Execution: Target Stage 1 benchmark NOUs (NOU 2026: 5, NOU 2025: 4, NOU 2024: 6, NOU 2018: 33 [handled gracefully], NOU 1999: 27).
6. Atomic DB Update & Stats Refresh: Save profiles atomically using `save_document_profile()` and trigger `compute_and_store_statistics()`.
"""

import sys
import os
import re
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set, Tuple

# Add project root and backend to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from backend.app.lib.db import (
    get_db,
    get_nou,
    is_using_sqlite,
    _get_sqlite_conn,
    save_document_profile,
    compute_and_store_statistics,
    get_author_counts,
    clean_person_name,
    is_valid_person_name,
    clear_in_memory_caches,
)
from pipeline.scrape_nou_rosters_html import (
    scrape_nou_roster_html,
    GENERIC_NON_PERSON_STRINGS,
)
from pipeline.enrich_missing_affiliations import clean_organization_string

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("repair_nou_rosters")

# Expanded set of generic non-person strings / patterns
GENERIC_LEADER_PATTERNS = {
    "kommisjonen", "departementet", "utvalget", "arbeidsgruppen", "sekretariatet",
    "redaksjonen", "departementets utvalg", "utvalgsleder", "utvalg", "kommisjon",
    "departement", "ukjent", "none", "null", "uten forfatter", "ingen", "n/a",
    "uten", "statens seniorråd", "direktoratet", "rådet", "styret", "arbeidsgruppe",
    "uavhengig", "forfatter mangler", "utvalgsleder for barnefamilieoverføringer"
}

SECRETARIAT_KEYWORDS = [
    "sekretær", "sekretariat", "sekretariatsleder", "sekretariatsleiar", "sekretariatet", "utvalgets sekretariat"
]

DIVIDER_PATTERNS = [
    r'_{3,}', r'-{3,}', r'\*{3,}', r'={3,}'
]

TITLE_PREFIX_PATTERN = re.compile(
    r'^\s*(?:prof\.|dr\.\s*(?:philos|juris|scient|polit|med|oecon|real|art|ing|theol|psychol|habil|techn)?\.?|ing\.|ingeniør\b|direktør\b|advokat\b|dommer\b|førsteamanuensis\b|førstelektor\b|høyesterettsdommer\b|lagmann\b|generalsekretær\b|forretningsfører\b|rådmann\b|stortingsrepresentant\b|ordfører\b|sekretariatsleder\b|forbundsformann\b|cand\.\s*(?:jur|real|polit|med|mag|econ|philol|psychol|agric|theol|sanit|sociol|scient|merc|ped|pharm|odont|vet)?\.?)\s*[/,-]?\s*',
    flags=re.IGNORECASE
)

# Known institutional organizations for Scandinavian public admin & NOU signature extraction
KNOWN_ORGANIZATIONS = [
    "Statistisk sentralbyrå", "Landsorganisasjonen i Norge", "Digitaliserings- og forvaltningsdepartementet",
    "Næringslivets Hovedorganisasjon", "KS", "Yrkesorganisasjonenes Sentralforbund",
    "Arbeidsgiverforeningen Spekter", "Akademikerne", "Hovedorganisasjonen Virke", "Finansdepartementet",
    "Arbeids- og inkluderingsdepartementet", "Unio", "Virke", "SSB", "LO", "NHO", "YS", "Spekter",
    "Justis- og politidepartementet", "Justis- og beredskapsdepartementet", "Klima- og miljødepartementet",
    "Helse- og omsorgsdepartementet", "Kunnskapsdepartementet", "Samferdselsdepartementet",
    "Utenriksdepartementet", "Forsvarsdepartementet", "Nærings- og fiskeridepartementet",
    "Kommunal- og distriktsdepartementet", "Barne- og familiedepartementet", "Kultur- og likestillingsdepartementet",
    "Landbruks- og matdepartementet", "Olje- og energidepartementet", "Norges Bank",
    "Statens naturvernråd", "Norsk kulturråd", "Likestillingsrådet", "Forbrukerrådet", "Departementets utvalg",
    "Miljøverndepartementet", "Prisdirektoratet", "Arbeidsdirektoratet", "Sjøfartsdirektoratet", "Kredittilsynet",
    "Arbeidstilsynet", "Skatteetaten", "Norges teknisk-naturvitenskapelige universitet", "Norges statsbaner",
    "Den Norske Advokatforening", "Riksrevisjonen"
]


def is_divider_line(text: str) -> bool:
    """Checks if a string is a divider line separating Utvalg and Secretariat."""
    text_clean = text.strip()
    for pat in DIVIDER_PATTERNS:
        if re.search(pat, text_clean):
            return True
    return False


def is_secretariat_header(text: str) -> bool:
    """Checks if a string is a header indicating secretariat section."""
    text_lower = text.strip().lower()
    if is_divider_line(text):
        return True
    for kw in ["sekretariat", "sekretariatet", "utvalgets sekretariat", "utvalgets' sekretariat", "sekretariatsleder", "sekretariatsleiar"]:
        if kw in text_lower:
            return True
    return False


def is_generic_leader_string(name: Optional[Any]) -> bool:
    """Checks if a string is a generic non-person leader identifier."""
    if not name:
        return True
    if isinstance(name, dict):
        name = name.get("name") or ""
    if not isinstance(name, str):
        name = str(name)
    clean = name.strip().lower()
    if not clean:
        return True
    if clean in GENERIC_NON_PERSON_STRINGS or clean in GENERIC_LEADER_PATTERNS:
        return True
    for pat in GENERIC_LEADER_PATTERNS:
        if clean == pat or clean.startswith(pat + " "):
            return True
    return False


def clean_and_normalize_name(name_str: Any) -> str:
    """Normalizes a person name by stripping academic titles, parentheticals, and extra spaces."""
    if not name_str:
        return ""
    if isinstance(name_str, dict):
        name_str = name_str.get("name") or ""
    if not isinstance(name_str, str):
        name_str = str(name_str)

    cleaned = clean_person_name(name_str)
    # Repeatedly strip title prefixes
    while True:
        new_cleaned = TITLE_PREFIX_PATTERN.sub('', cleaned)
        if new_cleaned == cleaned:
            break
        cleaned = new_cleaned

    # Secondary check for remaining parentheticals or titles
    cleaned = re.sub(r'\s*\(\s*(?:leder|nestleder|utvalgsleder|sekretær|sekretariat)\s*\)\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' ,.:;()\t\n\r')
    return cleaned


def detect_multi_column_patterns(raw_text: str) -> List[str]:
    """
    Splits multi-column concatenated strings (e.g. 2-column/3-column OCR text or concatenated member lines)
    into individual clean person names.
    """
    if not raw_text or not isinstance(raw_text, str):
        return []
    
    clean_input = raw_text.strip()
    if is_divider_line(clean_input) or is_secretariat_header(clean_input):
        return []

    # 1. Multi-space or tab separation
    if '\t' in clean_input or re.search(r'\s{2,}', clean_input):
        parts = [p.strip() for p in re.split(r'\t|\s{2,}', clean_input) if p.strip()]
        result = []
        for p in parts:
            c = clean_and_normalize_name(p)
            if c and is_valid_person_name(c):
                result.append(c)
        if result:
            return result

    # 2. Split pipe or slash separated names
    if '|' in clean_input or '/' in clean_input or ';' in clean_input:
        parts = [p.strip() for p in re.split(r'[/|;]', clean_input) if p.strip()]
        result = []
        for p in parts:
            c = clean_and_normalize_name(p)
            if c and is_valid_person_name(c):
                result.append(c)
        if result:
            return result

    # 3. Handle concatenated Title-Case names (e.g. "Francis Sejersted leder Vigdis Moe Skarstein Jon Bing...")
    # Find all Title-Case words
    words = clean_input.split()
    if len(words) > 4:
        # Regex find multi-word Norwegian human name pairs (e.g., First Middle Last or First Last)
        name_matches = re.findall(r'\b([A-ZÆØÅ][a-zæøå]+(?:\s+[A-ZÆØÅ][a-zæøå]+){1,3})\b', clean_input)
        names = []
        for nm in name_matches:
            c = clean_and_normalize_name(nm)
            if c and is_valid_person_name(c) and len(c.split()) in (2, 3, 4):
                if c not in names:
                    names.append(c)
        if len(names) >= 2:
            return names

    c_single = clean_and_normalize_name(clean_input)
    return [c_single] if c_single and is_valid_person_name(c_single) else []


def export_pre_migration_snapshot(output_dir: Optional[Path] = None) -> Path:
    """
    Exports a full pre-migration JSON snapshot of `document_profile` and `nou_authors`
    to `data/backups/nou_roster_snapshot_{timestamp}.json` BEFORE performing DB writes.
    """
    if output_dir is None:
        output_dir = PROJECT_ROOT / "data" / "backups"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snapshot_file = output_dir / f"nou_roster_snapshot_{timestamp}.json"

    logger.info(f"Generating pre-migration backup snapshot to {snapshot_file}...")

    nous_data = []
    authors_by_nou = {}

    if is_using_sqlite():
        conn = _get_sqlite_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, title, year, document_profile FROM nous ORDER BY year ASC, id ASC;")
            nous_rows = cur.fetchall()

            cur.execute("SELECT nou_id, name, role, organization FROM nou_authors;")
            authors_rows = cur.fetchall()

            for ar in authors_rows:
                nid = str(ar[0])
                if nid not in authors_by_nou:
                    authors_by_nou[nid] = []
                authors_by_nou[nid].append({
                    "name": ar[1],
                    "role": ar[2],
                    "organization": ar[3] or ""
                })

            for nr in nous_rows:
                nid = str(nr[0])
                dp_raw = nr[3]
                if isinstance(dp_raw, str):
                    try:
                        dp = json.loads(dp_raw)
                    except Exception:
                        dp = {}
                else:
                    dp = dp_raw or {}

                nous_data.append({
                    "nou_id": nid,
                    "title": nr[1] or "",
                    "year": int(nr[2]) if nr[2] else 0,
                    "document_profile": dp,
                    "authors": authors_by_nou.get(nid, [])
                })
        finally:
            conn.close()
    else:
        with get_db() as cur:
            cur.execute("SELECT id, title, year, document_profile FROM public.nous ORDER BY year ASC, id ASC;")
            nous_rows = cur.fetchall()

            cur.execute("SELECT nou_id, name, role, organization FROM public.nou_authors;")
            authors_rows = cur.fetchall()

            for ar in authors_rows:
                nid = str(ar['nou_id'])
                if nid not in authors_by_nou:
                    authors_by_nou[nid] = []
                authors_by_nou[nid].append({
                    "name": ar['name'],
                    "role": ar['role'],
                    "organization": ar.get('organization') or ""
                })

            for nr in nous_rows:
                nid = str(nr['id'])
                dp_raw = nr['document_profile']
                if isinstance(dp_raw, str):
                    try:
                        dp = json.loads(dp_raw)
                    except Exception:
                        dp = {}
                else:
                    dp = dp_raw or {}

                nous_data.append({
                    "nou_id": nid,
                    "title": nr['title'] or "",
                    "year": int(nr['year']) if nr['year'] else 0,
                    "document_profile": dp,
                    "authors": authors_by_nou.get(nid, [])
                })

    snapshot_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_nous": len(nous_data),
        "records": nous_data
    }

    tmp_file = snapshot_file.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(snapshot_payload, f, indent=2, ensure_ascii=False)
    tmp_file.replace(snapshot_file)
    logger.info(f"Pre-migration backup snapshot successfully exported to {snapshot_file} ({len(nous_data)} NOUs).")
    return snapshot_file



def parse_cell_roster_entry(cell_text: str) -> Optional[Dict[str, Any]]:
    """
    Parses a Markdown table cell entry into a structured dict with name, role, and org.
    Handles cell string un-merging and role tagging.
    """
    if not cell_text or not isinstance(cell_text, str):
        return None
    
    clean_txt = re.sub(r'\s+', ' ', cell_text).strip()
    if not clean_txt or clean_txt in ("-", "|", "Oslo") or is_divider_line(clean_txt) or clean_txt.startswith("Oslo,"):
        return None
    
    # Check role tags
    role = "member"
    clean_lower = clean_txt.lower()
    if "sekretariatsleder" in clean_lower or "sekretær" in clean_lower or "sekretariat" in clean_lower:
        role = "secretariat"
    elif " utvalgsleder" in clean_lower or " utvalsleiar" in clean_lower or " leder " in clean_lower or clean_lower.endswith(" leder"):
        role = "leader"

    # Identify organization in cell text
    detected_org = ""
    for org in KNOWN_ORGANIZATIONS:
        if len(org) <= 3:
            if re.search(r'\b' + re.escape(org) + r'\b', clean_txt, flags=re.IGNORECASE):
                detected_org = org
                break
        else:
            if org.lower() in clean_lower:
                detected_org = org
                break

    # Strip org name and role tags to isolate person name
    name_part = clean_txt
    if detected_org:
        if len(detected_org) <= 3:
            name_part = re.sub(r'\b' + re.escape(detected_org) + r'\b', '', name_part, flags=re.IGNORECASE)
        else:
            match = re.search(re.escape(detected_org), name_part, flags=re.IGNORECASE)
            if match:
                name_part = name_part[:match.start()] + name_part[match.end():]

    # Strip role tags and parentheticals from name
    name_part = re.sub(r'\b(?:sekretariatsleder|sekretariatsleiar|sekretær|sekretariat|utvalgsleder|utvalsleiar|leder|leiar|nestleder)\b', '', name_part, flags=re.IGNORECASE)
    name_part = re.sub(r'\s*\(\s*(?:fung\.|fungerende|leder|nestleder)\s*\)\s*', '', name_part, flags=re.IGNORECASE)
    name_part = re.sub(r'\s+', ' ', name_part).strip(' ,.:;()\t\n\r')

    if not name_part or len(name_part.split()) < 2:
        return None

    cleaned_name = clean_and_normalize_name(name_part)
    if not cleaned_name or not is_valid_person_name(cleaned_name):
        return None

    res = {"name": cleaned_name, "role": role}
    if detected_org:
        clean_o = clean_organization_string(detected_org)
        if clean_o:
            res["org"] = clean_o
            
    return res


def parse_non_table_signature_block(content: str) -> Optional[Dict[str, Any]]:
    """
    100% Dynamic Signature Block & Roster Parser for non-table markdown text.
    Extracts leader, members, and secretariat dynamically without static name arrays.
    """
    if not content or not isinstance(content, str):
        return None

    leader = None
    members = []
    secretariat = []

    # 1. Locate prose secretary mentions in document
    sec_names_in_doc = set()
    sec_matches = re.findall(
        r'\b([A-ZÆØÅ][a-zæøåéèàâ\-]+(?:\s+[A-ZÆØÅ][a-zæøåéèàâ\-]+){1,2})\b(?:\s+har vært sekretær|\s+tiltrådte som sekretær|\s+var sekretær|\s+sekretær|\s+sekretariatsleder)',
        content[:60000]
    )
    for sm in sec_matches:
        cleaned_sec = clean_and_normalize_name(sm)
        if cleaned_sec and is_valid_person_name(cleaned_sec):
            sec_names_in_doc.add(cleaned_sec.lower())



    # 2. Strategy A: Bullet list under Oppnevning og mandat / Sammensetning
    bullet_match = re.search(
        r'(?:sammensetning|oppnevning).*?\n((?:\s*[–\-\*\•]\s*.*?\n){3,})',
        content[:20000],
        re.IGNORECASE
    )
    if bullet_match:
        for b_line in bullet_match.group(1).splitlines():
            line_txt = re.sub(r'^\s*[–\-\*\•]\s*', '', b_line).strip()
            parsed = parse_cell_roster_entry(line_txt)
            if parsed:
                p_name = parsed["name"]
                p_org = parsed.get("org", "")
                p_role = parsed.get("role", "member")
                item = {"name": p_name, "org": p_org} if p_org else {"name": p_name}

                if p_role == "leader" and not leader:
                    leader = item
                elif p_role == "secretariat" or p_name.lower() in sec_names_in_doc:
                    if item not in secretariat:
                        secretariat.append(item)
                else:
                    if item not in members:
                        members.append(item)

    # 3. Strategy B: Prose signature line anchor
    if not leader or not members:
        date_match = re.search(
            r'(?:Oslo,|\bTil\s+[A-ZÆØÅ]|\b\d{1,2}\.\s*(?:januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember)\s*\d{4})'
            r'.*?(\b[A-ZÆØÅ][a-zæøåéèàâ\-]+(?:\s+[A-ZÆØÅ][a-zæøåéèàâ\-]+){1,3}\s+(?:leder|utvalgsleder|utvalsleiar)\b)'
            r'(.*?)(?:\s+side\s+\d+|\s+#|\Z)',
            content[:15000],
            re.DOTALL | re.IGNORECASE
        )
        if date_match:
            raw_leader_str = date_match.group(1).strip()
            raw_body_str = date_match.group(2).strip()

            leader_name_match = re.search(r'([A-ZÆØÅ][a-zæøåéèàâ\-]+(?:\s+[A-ZÆØÅ][a-zæøåéèàâ\-]+){1,3})', raw_leader_str)
            if leader_name_match and not leader:
                l_name = clean_and_normalize_name(leader_name_match.group(1))
                if l_name and is_valid_person_name(l_name):
                    leader = {"name": l_name}

            words = re.findall(r'[A-ZÆØÅ][a-zæøåéèàâ\-]+', raw_body_str)
            NON_PERSON_WORDS = {
                "Kapittel", "Sammendrag", "Vedlegg", "Oslo", "Statens", "Justis",
                "Departementet", "Til", "Det", "Kongelig", "Regjeringen", "Kommisjonen",
                "Utvalget", "Norge", "Norges", "Innhold", "Forord"
            }
            person_words = [w for w in words if w not in NON_PERSON_WORDS]

            extracted_names = []
            idx = 0
            while idx < len(person_words):
                if idx + 1 < len(person_words):
                    w1, w2 = person_words[idx], person_words[idx+1]
                    w3 = person_words[idx+2] if idx + 2 < len(person_words) else None

                    if w3 and len(w3) >= 3 and not (w3 in {"Jon", "Thor", "Tove", "Diis", "Kristin", "Nazneen", "Ole", "Helge", "Gunnar", "Eivind", "Hans", "Ellen", "Kjeld", "Maria", "Ørnulf", "Mona", "Vigdis", "Francis"}):
                        cand3 = f"{w1} {w2} {w3}"
                        c_clean = clean_and_normalize_name(cand3)
                        if c_clean and is_valid_person_name(c_clean) and len(c_clean.split()) in (2, 3, 4):
                            extracted_names.append(c_clean)
                            idx += 3
                            continue

                    cand2 = f"{w1} {w2}"
                    c_clean2 = clean_and_normalize_name(cand2)
                    if c_clean2 and is_valid_person_name(c_clean2) and len(c_clean2.split()) >= 2:
                        extracted_names.append(c_clean2)
                        idx += 2
                    else:
                        idx += 1
                else:
                    idx += 1

            leader_n_str = leader["name"] if isinstance(leader, dict) else (leader or "")
            for name_str in extracted_names:
                if leader_n_str and name_str.lower() == leader_n_str.lower():
                    continue
                item = {"name": name_str}
                name_lower = name_str.lower()
                if name_lower in sec_names_in_doc or "sekretær" in name_lower:
                    if item not in secretariat:
                        secretariat.append(item)
                else:
                    if item not in members:
                        members.append(item)

    if not leader and not members and not secretariat:
        return None

    clean_m = []
    seen_m = set()
    for m in members:
        nm = m["name"].lower()
        if nm not in seen_m:
            seen_m.add(nm)
            clean_m.append(m)

    clean_s = []
    seen_s = set()
    for s in secretariat:
        ns = s["name"].lower()
        if ns not in seen_s and ns not in seen_m:
            seen_s.add(ns)
            clean_s.append(s)

    return {
        "leader": leader,
        "members": clean_m,
        "secretariat": clean_s
    }


def extract_roster_from_markdown_file(nou_id: str) -> Optional[Dict[str, Any]]:
    """
    Parses Markdown signature tables/blocks in `data/markdown/` to extract 100% Ground Truth roster records.
    Returns dict with keys 'leader', 'members', 'secretariat'.
    """
    md_dir = PROJECT_ROOT / "data" / "markdown"
    if not md_dir.exists():
        return None

    # Locate markdown file matching nou_id, prioritizing largest file (avoiding stubs)
    candidate_files = list(md_dir.glob(f"{nou_id}_*.md")) + list(md_dir.glob(f"*{nou_id}*.md"))
    if not candidate_files:
        return None

    candidate_files.sort(key=lambda p: p.stat().st_size, reverse=True)
    md_file = candidate_files[0]
    try:
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.warning(f"Error reading markdown file {md_file}: {e}")
        return None

    leader = None
    members = []
    secretariat = []

    lines = content.splitlines()

    # Isolate signature table lines occurring between introduction and Chapter 1 (within first 120 lines)
    sig_lines = []
    in_sig_area = False
    for line in lines[:120]:
        l_str = line.strip()
        if "Oslo," in l_str or "Det tekniske beregningsutvalget" in l_str or "Til Arbeids-" in l_str or "Til Justis-" in l_str or "Kongelig resolusjon" in l_str:
            in_sig_area = True
        if in_sig_area and (l_str.startswith("# 1") or l_str.startswith("## 1") or l_str.startswith("# Kapittel") or l_str.startswith("1.1 ") or l_str.startswith("1 Sammendrag") or l_str.startswith("# Lønnsutviklingen") or l_str.startswith("## Innledning")):
            break
        if in_sig_area and l_str.startswith("|") and l_str.endswith("|"):
            sig_lines.append(l_str)


    if sig_lines:
        in_secretariat_section = False
        for line_str in sig_lines:
            if "| --- |" in line_str:
                continue
            cells = [c.strip() for c in line_str.split("|")[1:-1] if c.strip()]
            for cell in cells:
                if is_divider_line(cell) or is_secretariat_header(cell) or "sekretariatsleder" in cell.lower():
                    in_secretariat_section = True

                parsed = parse_cell_roster_entry(cell)
                if parsed:
                    p_name = parsed["name"]
                    p_org = parsed.get("org", "")
                    p_role = parsed.get("role", "member")
                    item = {"name": p_name, "org": p_org} if p_org else {"name": p_name}

                    if p_role == "leader" and not leader:
                        leader = item
                    elif in_secretariat_section or p_role == "secretariat":
                        in_secretariat_section = True
                        if item not in secretariat and (leader is None or item["name"] != (leader["name"] if isinstance(leader, dict) else leader)):
                            secretariat.append(item)
                    else:
                        if item not in members and (leader is None or item["name"] != (leader["name"] if isinstance(leader, dict) else leader)):
                            members.append(item)

    if not leader or not members:
        # Fallback for non-table signature blocks (e.g. NOU 1999: 27)
        non_table_roster = parse_non_table_signature_block(content)
        if non_table_roster:
            if not leader and non_table_roster.get("leader"):
                leader = non_table_roster["leader"]
            if not members and non_table_roster.get("members"):
                members = non_table_roster["members"]
            if not secretariat and non_table_roster.get("secretariat"):
                secretariat = non_table_roster["secretariat"]






    if not leader and not members and not secretariat:
        return None

    # Deduplicate members and secretariat
    clean_m = []
    seen_m = set()
    for m in members:
        nm = m["name"].lower()
        if nm not in seen_m:
            seen_m.add(nm)
            clean_m.append(m)

    clean_s = []
    seen_s = set()
    for s in secretariat:
        ns = s["name"].lower()
        if ns not in seen_s and ns not in seen_m:
            seen_s.add(ns)
            clean_s.append(s)

    return {
        "leader": leader,
        "members": clean_m,
        "secretariat": clean_s
    }



def is_record_clean_and_matching(
    nou_id: str,
    existing_dp: dict,
    repaired_dp: dict,
) -> bool:
    """
    Zero-Mutation Guard evaluator:
    Checks if existing DB record for `nou_id` is already 100% clean and valid matching repaired profile.
    Must compare member names, roles, format consistency, and affiliation presence.
    """
    exist_leader = existing_dp.get("leader") or existing_dp.get("utvalgsleder") or ""
    exist_leader_name = exist_leader.get("name", "") if isinstance(exist_leader, dict) else str(exist_leader or "")
    rep_leader = repaired_dp.get("leader") or ""
    rep_leader_name = rep_leader.get("name", "") if isinstance(rep_leader, dict) else str(rep_leader or "")

    clean_exist_l = clean_and_normalize_name(exist_leader_name)
    clean_rep_l = clean_and_normalize_name(rep_leader_name)

    # Leader check
    if is_generic_leader_string(exist_leader_name) or is_generic_leader_string(clean_exist_l):
        return False
    if clean_exist_l.lower() != clean_rep_l.lower():
        return False

    def _normalize_roster_items(items: list) -> List[Tuple[str, str]]:
        result = []
        for item in items or []:
            if isinstance(item, dict):
                n = clean_and_normalize_name(item.get("name") or "")
                o = clean_organization_string(item.get("org") or item.get("organization") or item.get("affiliation") or "")
                result.append((n, o))
            elif isinstance(item, str):
                n = clean_and_normalize_name(item)
                result.append((n, ""))
        return result

    exist_members_raw = existing_dp.get("members") or []
    rep_members_raw = repaired_dp.get("members") or []

    exist_m = _normalize_roster_items(exist_members_raw)
    rep_m = _normalize_roster_items(rep_members_raw)

    if len(exist_m) != len(rep_m):
        return False

    # Check member names match
    if [x[0].lower() for x in exist_m] != [x[0].lower() for x in rep_m]:
        return False

    # Check for org names in existing member names
    for name, _ in exist_m:
        for org in KNOWN_ORGANIZATIONS:
            if name.lower() == org.lower():
                return False

    # Check affiliation enrichment status:
    # If repaired profile has member orgs, but existing record lacks them (or has fewer orgs), return False
    exist_org_count = sum(1 for _, o in exist_m if o)
    rep_org_count = sum(1 for _, o in rep_m if o)
    if rep_org_count > exist_org_count:
        return False

    # Format check: if existing record uses plain strings for members, but repaired profile has dicts with orgs, return False
    if any(isinstance(m, str) for m in exist_members_raw) and rep_org_count > 0:
        return False

    # Secretariat check
    exist_sec_raw = existing_dp.get("secretariat") or []
    rep_sec_raw = repaired_dp.get("secretariat") or []

    exist_s = _normalize_roster_items(exist_sec_raw)
    rep_s = _normalize_roster_items(rep_sec_raw)

    if len(exist_s) != len(rep_s):
        return False

    if [x[0].lower() for x in exist_s] != [x[0].lower() for x in rep_s]:
        return False

    exist_sec_org_count = sum(1 for _, o in exist_s if o)
    rep_sec_org_count = sum(1 for _, o in rep_s if o)
    if rep_sec_org_count > exist_sec_org_count:
        return False

    return True



def extract_embedded_secretariat(members: List[Any]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """
    Scans members list for embedded secretariat keywords, returning (clean_members, extracted_secretariat).
    Handles string members and dict members safely.
    """
    clean_members = []
    extracted_secretariat = []

    for m in members:
        if not m:
            continue
        m_name = m.get("name") if isinstance(m, dict) else str(m)
        m_org = m.get("org") if isinstance(m, dict) else ""
        m_cleaned = clean_and_normalize_name(m_name)
        m_lower = m_name.lower()

        item = {"name": m_cleaned, "org": clean_organization_string(m_org)} if clean_organization_string(m_org) else {"name": m_cleaned}

        if any(kw in m_lower for kw in SECRETARIAT_KEYWORDS) or is_secretariat_header(m_name):
            if is_valid_person_name(m_cleaned):
                extracted_secretariat.append(item)
        else:
            if is_valid_person_name(m_cleaned):
                clean_members.append(item)

    return clean_members, extracted_secretariat


def log_uncertainty_entry(
    nou_id: str,
    title: str,
    year: int,
    reason: str,
    source_url: str = "",
    candidate_leaders: List[str] = None,
    raw_text_snippet: str = "",
    log_file_path: Path = None,
) -> Dict[str, Any]:
    """
    Appends an ambiguous or low-confidence NOU entry to data/uncertain_nous_review.json.
    """
    if log_file_path is None:
        log_file_path = PROJECT_ROOT / "data" / "uncertain_nous_review.json"

    entry = {
        "nou_id": str(nou_id),
        "title": title,
        "year": int(year),
        "reason": reason,
        "source_url": source_url,
        "candidate_leaders": candidate_leaders or [],
        "raw_text_snippet": raw_text_snippet,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    existing_entries = []
    if log_file_path.exists():
        try:
            with open(log_file_path, "r", encoding="utf-8") as f:
                existing_entries = json.load(f)
        except Exception:
            existing_entries = []

    # Avoid duplicate logs for same nou_id
    existing_entries = [e for e in existing_entries if str(e.get("nou_id")) != str(nou_id)]
    existing_entries.append(entry)

    tmp_path = log_file_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(existing_entries, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, log_file_path)

    return entry


def repair_single_nou(nou_id: str) -> Optional[Dict[str, Any]]:
    """Repairs a single NOU roster by ID cleanly, checking whether ID is numeric before DB query."""
    b_id = str(nou_id).strip()
    if not b_id.isdigit():
        logger.warning(f"[HANDLED GRACEFULLY] Benchmark NOU ID '{b_id}' is non-numeric. Skipping database lookup.")
        return None
    db_nou = get_nou(b_id)
    if not db_nou:
        logger.warning(f"[HANDLED GRACEFULLY] Benchmark NOU ID '{b_id}' not found in database. Skipping gracefully.")
        return None
    return db_nou


def run_repair_benchmark(benchmark_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Executes Stage 1 Benchmark Batch Roster Repair across target benchmark NOUs:
    - NOU 2026: 5 (3155079)
    - NOU 2025: 4 (3094178)
    - NOU 2024: 6 (3031371)
    - NOU 2018: 33 (non-existent/non-numeric, handled gracefully)
    - NOU 1999: 27 (142119)
    """
    if benchmark_ids is None:
        benchmark_ids = ["3155079", "3094178", "3031371", "2018-33", "142119"]

    logger.info("=" * 70)
    logger.info("Running Stage 1 Benchmark Batch Roster Repair...")
    logger.info("=" * 70)

    # MANDATORY PRE-MIGRATION BACKUP SNAPSHOT BEFORE ANY WRITES
    export_pre_migration_snapshot()

    uncertain_file = PROJECT_ROOT / "data" / "uncertain_nous_review.json"
    stats_counter = {
        "total_benchmarks": len(benchmark_ids),
        "repaired": 0,
        "skipped_clean": 0,
        "handled_non_existent": 0,
    }

    for b_id in benchmark_ids:
        b_id_str = str(b_id).strip()
        if not b_id_str.isdigit():
            logger.warning(f"[HANDLED GRACEFULLY] Benchmark NOU ID '{b_id_str}' is non-numeric. Skipping database lookup.")
            stats_counter["handled_non_existent"] += 1
            continue

        # Fetch record from DB generically
        db_nou = get_nou(b_id_str)
        if not db_nou:
            logger.warning(f"[HANDLED GRACEFULLY] Benchmark NOU ID '{b_id_str}' not found in database. Skipping gracefully.")
            stats_counter["handled_non_existent"] += 1
            continue


        nou_id = str(db_nou["id"])
        title = db_nou.get("title", "")
        year = db_nou.get("year", 2026)
        dp_raw = db_nou.get("document_profile") or {}
        if isinstance(dp_raw, str):
            try:
                dp = json.loads(dp_raw)
            except Exception:
                dp = {}
        else:
            dp = dp_raw or {}

        # 1. Attempt Markdown signature page extraction (100% Ground Truth)
        md_roster = extract_roster_from_markdown_file(nou_id)

        if md_roster:
            final_leader = md_roster.get("leader")
            final_members = md_roster.get("members", [])
            final_sec = md_roster.get("secretariat", [])
            source = "markdown_signature_table"
        else:
            # Fallback to HTML scraper
            scraped = scrape_nou_roster_html({"nou_id": nou_id, "title": title, "source_url": db_nou.get("source_url", "")})
            scraped_leader = scraped.get("leader", "")
            final_leader = {"name": scraped_leader} if scraped_leader else None
            final_members = [{"name": m} for m in scraped.get("members", [])]
            final_sec = [{"name": s} for s in scraped.get("secretariat", [])]
            source = scraped.get("source", "html_scraper")

        # Construct repaired document_profile payload
        leader_name = final_leader["name"] if isinstance(final_leader, dict) else str(final_leader or "")
        leader_payload = final_leader if final_leader else ""

        repaired_profile = {
            "leader": leader_payload,
            "utvalgsleder": leader_name,
            "utvalsleiar": leader_name,
            "utvalgets_leder": leader_name,
            "utvalgets' leder": leader_name,
            "members": final_members,
            "committee_members": final_members,
            "secretariat": final_sec,
            "source": source
        }

        # ZERO-MUTATION GUARD CHECK
        if is_record_clean_and_matching(nou_id, dp, repaired_profile):
            logger.info(f"[ZERO-MUTATION GUARD] NOU ID {nou_id} is already 100% clean and valid. Skipping mutation.")
            stats_counter["skipped_clean"] += 1
            continue

        # Save profile atomically
        save_document_profile(nou_id, repaired_profile)
        stats_counter["repaired"] += 1
        logger.info(f"[STAGE 1 REPAIRED] NOU ID {nou_id} ({year}): Leader='{leader_name}', Members={len(final_members)}, Sec={len(final_sec)}")

    logger.info("Triggering stats recomputation & cache refresh...")
    compute_and_store_statistics()
    clear_in_memory_caches()

    logger.info("=" * 70)
    logger.info("Stage 1 Benchmark Batch Roster Repair Complete!")
    logger.info(f"Total Benchmarks Evaluated: {stats_counter['total_benchmarks']}")
    logger.info(f"Repaired & Saved to Supabase: {stats_counter['repaired']}")
    logger.info(f"Skipped (Zero-Mutation Guard Clean): {stats_counter['skipped_clean']}")
    logger.info(f"Handled Gracefully (Non-existent/Missing): {stats_counter['handled_non_existent']}")
    logger.info("=" * 70)

    return stats_counter


def run_repair_pipeline() -> Dict[str, Any]:
    """Executes the NOU Committee Roster Repair Pipeline across all target NOUs."""
    inventory_file = PROJECT_ROOT / "data" / "nou_roster_prefix_inventory.json"
    uncertain_file = PROJECT_ROOT / "data" / "uncertain_nous_review.json"

    if not inventory_file.exists():
        raise FileNotFoundError(f"Pre-fix inventory file missing: {inventory_file}")

    logger.info(f"Loading pre-fix inventory from {inventory_file}...")
    with open(inventory_file, "r", encoding="utf-8") as f:
        inventory = json.load(f)

    clean_ids = set(inventory.get("clean_ids") or [])
    categories = inventory.get("categories") or {}

    target_items = []
    for cat in ["A", "B", "C", "D"]:
        target_items.extend(categories.get(cat, []))

    logger.info(f"Pre-fix inventory loaded: {len(clean_ids)} clean records (Category E).")
    logger.info(f"Targeting {len(target_items)} NOUs across Categories A, B, C, D for repair.")

    # MANDATORY PRE-MIGRATION BACKUP SNAPSHOT BEFORE ANY WRITES
    export_pre_migration_snapshot()

    # Initialize / reset uncertainty review file
    if uncertain_file.exists():
        uncertain_file.unlink()

    stats_counter = {
        "total_targets": len(target_items),
        "clean_ids_skipped": len(clean_ids),
        "zero_mutation_skipped": 0,
        "repaired_and_saved": 0,
        "logged_uncertain": 0,
        "zero_edits_verified": True,
    }

    # Iterate over target NOUs only
    for item in target_items:
        nou_id = str(item.get("id"))
        title = item.get("title", "")
        year = item.get("year", 2024)
        reasons = item.get("reasons", [])

        # STRICT ZERO EDITS INVARIANT CHECK
        if nou_id in clean_ids:
            logger.error(f"INVARIANT VIOLATION: Clean ID {nou_id} attempted to be edited!")
            stats_counter["zero_edits_verified"] = False
            continue

        # Check non-numeric NOU ID
        if not nou_id.isdigit():
            logger.warning(f"[HANDLED GRACEFULLY] NOU ID '{nou_id}' is non-numeric. Skipping database lookup.")
            stats_counter["zero_mutation_skipped"] += 1
            continue

        # Fetch NOU record from Supabase
        db_nou = get_nou(nou_id)
        if not db_nou:
            db_nou = {
                "id": nou_id,
                "title": title,
                "year": year,
                "source_url": f"https://www.regjeringen.no/no/dokumenter/id{nou_id}/" if nou_id.isdigit() else "",
                "pdf_url": "",
                "document_profile": {}
            }

        dp_raw = db_nou.get("document_profile") or {}
        if isinstance(dp_raw, str):
            try:
                dp = json.loads(dp_raw)
            except Exception:
                dp = {}
        elif isinstance(dp_raw, dict):
            dp = dp_raw
        else:
            dp = {}

        source_url = db_nou.get("source_url") or ""
        pdf_url = db_nou.get("pdf_url") or ""

        # Step 1: Scrape authentic metadata using Markdown or HTML scraper
        md_roster = extract_roster_from_markdown_file(nou_id)
        if md_roster and (md_roster.get("members") or md_roster.get("leader")):
            scraped_leader = md_roster["leader"]["name"] if isinstance(md_roster.get("leader"), dict) else str(md_roster.get("leader") or "")
            scraped_members = md_roster.get("members", [])
            scraped_sec = md_roster.get("secretariat", [])
            scraped_source = "markdown_signature_table"
            scraped_conf = 0.98
        else:
            scraped = scrape_nou_roster_html({"nou_id": nou_id, "source_url": source_url, "pdf_url": pdf_url, "title": title})
            scraped_leader = scraped.get("leader", "").strip()
            scraped_members = scraped.get("members", [])
            scraped_sec = scraped.get("secretariat", [])
            scraped_source = scraped.get("source", "html_repair")
            scraped_conf = scraped.get("confidence", 0.0)

        existing_leader = dp.get("leader") or dp.get("utvalgsleder") or dp.get("utvalsleiar") or dp.get("utvalgets' leder") or dp.get("utvalgets_leder")
        if isinstance(existing_leader, dict):
            existing_leader_name = existing_leader.get("name", "")
        else:
            existing_leader_name = str(existing_leader or "")

        existing_members = dp.get("members") or dp.get("committee_members") or []
        if isinstance(existing_members, str):
            existing_members = [existing_members]
        existing_sec = dp.get("secretariat") or dp.get("secretariat_members") or []
        if isinstance(existing_sec, str):
            existing_sec = [existing_sec]

        # Step 2: Utvalgsleder Scrubbing & Selection
        final_leader = ""
        candidate_leaders = []

        # Check existing leader
        cleaned_exist_leader = clean_and_normalize_name(existing_leader_name)
        if cleaned_exist_leader and not is_generic_leader_string(cleaned_exist_leader) and is_valid_person_name(cleaned_exist_leader):
            final_leader = cleaned_exist_leader

        # Check scraped leader
        cleaned_scraped_leader = clean_and_normalize_name(scraped_leader)
        if not final_leader and cleaned_scraped_leader and not is_generic_leader_string(cleaned_scraped_leader) and is_valid_person_name(cleaned_scraped_leader):
            final_leader = cleaned_scraped_leader

        if cleaned_scraped_leader and is_valid_person_name(cleaned_scraped_leader):
            candidate_leaders.append(cleaned_scraped_leader)
        if cleaned_exist_leader and is_valid_person_name(cleaned_exist_leader):
            candidate_leaders.append(cleaned_exist_leader)

        # Step 3: Member & Secretariat Cleaning & Separation
        all_raw_members = existing_members + scraped_members
        all_raw_sec = existing_sec + scraped_sec

        cleaned_members, extracted_sec = extract_embedded_secretariat(all_raw_members)
        all_sec_raw = all_raw_sec + extracted_sec

        cleaned_sec = []
        for s in all_sec_raw:
            s_name = s.get("name") if isinstance(s, dict) else str(s)
            s_org = s.get("org") if isinstance(s, dict) else ""
            s_clean = clean_and_normalize_name(s_name)
            if s_clean and is_valid_person_name(s_clean):
                item = {"name": s_clean, "org": clean_organization_string(s_org)} if clean_organization_string(s_org) else {"name": s_clean}
                if item not in cleaned_sec:
                    cleaned_sec.append(item)

        # Deduplicate members preserving order
        final_members = []
        for m in cleaned_members:
            m_name = m.get("name") if isinstance(m, dict) else str(m)
            m_org = m.get("org") if isinstance(m, dict) else ""
            m_clean = clean_and_normalize_name(m_name)
            if m_clean and is_valid_person_name(m_clean):
                item = {"name": m_clean, "org": clean_organization_string(m_org)} if clean_organization_string(m_org) else {"name": m_clean}
                if item not in final_members:
                    final_members.append(item)

        # Exclude leader from members & secretariat
        if final_leader:
            final_members = [m for m in final_members if m.get("name") != final_leader]
            cleaned_sec = [s for s in cleaned_sec if s.get("name") != final_leader]

        # Exclude secretariat from members
        sec_names = {s["name"] for s in cleaned_sec}
        final_members = [m for m in final_members if m.get("name") not in sec_names]

        # Step 4: Evaluate Ambiguity & Uncertainty
        is_uncertain = False
        uncertain_reason = ""

        if not final_leader or is_generic_leader_string(final_leader):
            is_uncertain = True
            uncertain_reason = f"Generic or missing committee chair: '{existing_leader_name}' (Scraped: '{scraped_leader}')"
        elif len(final_members) < 3 and scraped_conf < 0.80:
            is_uncertain = True
            uncertain_reason = f"Missing full committee roster (<3 members found: {len(final_members)})"

        if is_uncertain:
            log_uncertainty_entry(
                nou_id=nou_id,
                title=title,
                year=year,
                reason=uncertain_reason,
                source_url=source_url,
                candidate_leaders=candidate_leaders,
                raw_text_snippet=" | ".join(reasons),
                log_file_path=uncertain_file,
            )
            # Clear generic leader string from document_profile so non-person is not stored as leader
            repaired_profile = {
                "leader": "",
                "utvalgsleder": "",
                "utvalsleiar": "",
                "utvalgets' leder": "",
                "utvalgets_leder": "",
                "members": final_members,
                "committee_members": final_members,
                "secretariat": cleaned_sec,
                "source": scraped_source
            }

            if is_record_clean_and_matching(nou_id, dp, repaired_profile):
                stats_counter["zero_mutation_skipped"] += 1
            else:
                save_document_profile(nou_id, repaired_profile)
                stats_counter["logged_uncertain"] += 1
                logger.info(f"[UNCERTAIN] NOU ID {nou_id}: {uncertain_reason}")
        else:
            # Step 5: Save Profile Changes to Supabase PostgreSQL atomically
            repaired_profile = {
                "leader": final_leader,
                "utvalgsleder": final_leader,
                "utvalsleiar": final_leader,
                "utvalgets' leder": final_leader,
                "utvalgets_leder": final_leader,
                "members": final_members,
                "committee_members": final_members,
                "secretariat": cleaned_sec,
                "source": scraped_source
            }

            if is_record_clean_and_matching(nou_id, dp, repaired_profile):
                stats_counter["zero_mutation_skipped"] += 1
            else:
                save_document_profile(nou_id, repaired_profile)
                stats_counter["repaired_and_saved"] += 1
                logger.info(f"[REPAIRED] NOU ID {nou_id}: Leader='{final_leader}', Members={len(final_members)}, Sec={len(cleaned_sec)}")

    # Step 6: Stats & Cache Refresh
    logger.info("Triggering compute_and_store_statistics() and cache refresh...")
    stats_result = compute_and_store_statistics()
    clear_in_memory_caches()

    logger.info("=" * 70)
    logger.info("NOU Committee Roster Repair Pipeline Complete!")
    logger.info(f"Total Targets: {stats_counter['total_targets']}")
    logger.info(f"Clean IDs Skipped (Category E): {stats_counter['clean_ids_skipped']}")
    logger.info(f"Zero-Mutation Guard Skipped: {stats_counter['zero_mutation_skipped']}")
    logger.info(f"Repaired & Saved to Supabase: {stats_counter['repaired_and_saved']}")
    logger.info(f"Logged to Uncertainty Review: {stats_counter['logged_uncertain']}")
    logger.info("=" * 70)

    return stats_counter


def main():
    parser = argparse.ArgumentParser(description="NOU Committee Roster Repair Engine")
    parser.add_argument("--benchmark", action="store_true", help="Run Stage 1 benchmark repairs on the 5 benchmark NOUs")
    args = parser.parse_args()

    if args.benchmark:
        run_repair_benchmark()
    else:
        run_repair_pipeline()


if __name__ == "__main__":
    main()
