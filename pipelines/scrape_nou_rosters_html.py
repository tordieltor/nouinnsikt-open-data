#!/usr/bin/env python3
"""
HTML-First Sourcing Engine for Committee Rosters, Chairs & Secretariats (Milestone 2)

Scrapes authentic committee rosters, human chairs (utvalgsleder), secretariats,
and affiliations directly from regjeringen.no Chapter 1 (?ch=1) HTML,
Nasjonalbiblioteket (NB.no) Catalog API metadata, and UiO Duo metadata pages.
"""

import os
import re
import json
import logging
import sys
from typing import Dict, List, Optional, Any, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from bs4 import BeautifulSoup

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scrape_nou_rosters_html")

# Non-person generic strings that must NEVER be accepted as human leaders
GENERIC_NON_PERSON_STRINGS = {
    "kommisjonen", "departementet", "utvalget", "arbeidsgruppen",
    "utvalgsleder for barnefamilieoverføringer", "departementets utvalg",
    "kommisjon", "sekretariatet", "redaksjonen"
}

STOP_WORDS = {
    "dokumentet", "neste", "kapittel", "sammendrag", "innhold", "forsiden",
    "last", "ned", "word", "pdf", "søkeresultat", "lenkeverktøy", "til", "innholdsfortegnelse"
}

_http_session: Optional[requests.Session] = None


def get_http_session() -> requests.Session:
    """Returns a shared requests.Session configured with HTTP 429 backoff retry logic."""
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        retry_strategy = Retry(
            total=4,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        _http_session.mount("https://", adapter)
        _http_session.mount("http://", adapter)
        _http_session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NOUinnsikt/1.0"})
    return _http_session


def clean_person_name(txt: str) -> str:
    """Cleans a person name string by removing role titles, stacked academic titles, and normalization noise."""
    if not txt:
        return ""

    # 1. Strip parenthetical role tags: (leder), (nestleder), (sekretær), (utvalgsleder), (sekretariatsleder), etc.
    txt = re.sub(
        r'\s*\(\s*(?:leder|nestleder|utvalgsleder|nestutvalgsleder|sekretariatsleder|sekretariat|sekretær)\s*\)\s*',
        ' ', txt, flags=re.IGNORECASE
    )

    # 2. Strip standalone role prefixes / suffixes (e.g. 'Leder: Kari Nordmann' or 'Kari Nordmann, nestleder')
    txt = re.sub(
        r'^\s*(?:leder|nestleder|utvalgsleder|nestutvalgsleder|sekretariatsleder|sekretariat|sekretær)\b:?\s*',
        ' ', txt, flags=re.IGNORECASE
    )
    txt = re.sub(
        r',?\s*\b(?:leder|nestleder|utvalgsleder|nestutvalgsleder|sekretariatsleder|sekretariat|sekretær)\b\s*$',
        ' ', txt, flags=re.IGNORECASE
    )

    # 3. Repeatedly strip leading academic and professional title prefixes
    title_pattern = re.compile(
        r'^\s*(?:prof\.|dr\.\s*(?:philos|juris|scient|polit|med|oecon|real|art|ing|theol|psychol|habil|techn)?\.?|ing\.|ingeniør\b|direktør\b|advokat\b|dommer\b|førsteamanuensis\b|førstelektor\b|høyesterettsdommer\b|lagmann\b|leder\b|nestleder\b|cand\.\s*(?:jur|real|polit|med|mag|econ|philol|psychol|agric|theol|sanit|sociol|scient|merc|ped|pharm|odont|vet)?\.?)\s*[/,-]?\s*',
        flags=re.IGNORECASE
    )
    while True:
        new_txt = title_pattern.sub('', txt)
        if new_txt == txt:
            break
        txt = new_txt

    # 4. Normalize spaces and surrounding punctuation
    txt = re.sub(r'\s+', ' ', txt).strip(' ,.:;()\t\n\r')
    return txt


def format_creator_name(creator: str) -> str:
    """Formats 'Surname, Firstname' into 'Firstname Surname'."""
    if not creator:
        return ""
    creator = creator.strip()
    if "," in creator:
        parts = creator.split(",", 1)
        return f"{parts[1].strip()} {parts[0].strip()}".strip()
    return creator


def is_valid_person_name(name: str) -> bool:
    """Validates that a string represents a plausible human name."""
    if not name or len(name) < 3 or len(name) > 60:
        return False
    lower = name.lower()
    if lower in GENERIC_NON_PERSON_STRINGS:
        return False
    words = name.split()
    if len(words) < 2 or len(words) > 5:
        return False
    if any(ch.isdigit() for ch in name):
        return False
    if any(w.lower() in STOP_WORDS for w in words):
        return False
    return True


def extract_affiliations_from_line(line: str) -> Tuple[str, str]:
    """
    Extracts person name and affiliation from line if present in format:
    'Navn (Affiliation)' or 'Navn, Affiliation'.
    """
    line = line.strip()
    # Check parenthetical affiliation: e.g. "Hanne Blekkan (Universitetet i Bergen)"
    m_paren = re.search(r'^([^(]+)\(([^)]+)\)', line)
    if m_paren:
        name_part = clean_person_name(m_paren.group(1))
        aff_part = m_paren.group(2).strip()
        if aff_part.lower() not in ["leder", "sekretariatsleder", "sekretær", "utvalgsleder", "nestleder"]:
            return name_part, aff_part
        return name_part, ""

    # Check comma affiliation if name part looks like a name
    if "," in line:
        parts = line.split(",", 1)
        possible_name = clean_person_name(parts[0])
        if is_valid_person_name(possible_name):
            return possible_name, parts[1].strip()

    return clean_person_name(line), ""


def fetch_regjeringen_ch1_html(source_url: str) -> dict:
    """
    Parses regjeringen.no `?ch=1` HTML landing page for signature blocks,
    extracting human chair (`Leder` / `(leder)`), members list, secretariat list, and affiliations.
    """
    result = {
        "leader": "",
        "members": [],
        "secretariat": [],
        "affiliations": [],
        "source": "regjeringen_html",
        "confidence": 0.0
    }

    if not source_url:
        return result

    # Normalize source_url to regjeringen ?ch=1 endpoint
    url = source_url.strip()
    if re.match(r'^(id)?\d+$', url):
        clean_id = re.sub(r'\D', '', url)
        url = f"https://www.regjeringen.no/no/dokumenter/id{clean_id}/?ch=1"
    elif "regjeringen.no" in url:
        if "?ch=" not in url:
            if url.endswith("/"):
                url = url + "?ch=1"
            else:
                url = url + "/?ch=1"

    try:
        session = get_http_session()
        r = session.get(url, timeout=(5.0, 15.0))
        if r.status_code != 200:
            logger.warning(f"Regjeringen HTML returned status {r.status_code} for {url}")
            return result

        soup = BeautifulSoup(r.text, "html.parser")
        main = soup.find("main") or soup.find("article") or soup.body
        if not main:
            return result

        raw_lines = []
        for elem in main.find_all(['p', 'h1', 'h2', 'h3', 'div', 'li']):
            text = elem.get_text('\n').strip()
            if text:
                for sub in text.split('\n'):
                    sub_s = sub.strip()
                    if sub_s:
                        raw_lines.append(sub_s)

        leader = ""
        members = []
        secretariat = []
        affiliations_map = {}

        mode = "search_leader"

        for i, line in enumerate(raw_lines):
            lower = line.lower().strip()

            # Stop conditions if we hit document footer / next chapter links
            if any(stop_key in lower for stop_key in ["dokumentet i pdf", "last ned", "til forsiden", "søk i dokumentet"]):
                if leader:
                    break

            if mode == "search_leader":
                if lower in ["leder", "(leder)", "utvalgsleder", "kommisjonsleder"] and i > 0:
                    cand = clean_person_name(raw_lines[i - 1])
                    if is_valid_person_name(cand):
                        leader = cand
                        mode = "in_members"
                elif " leder" in lower or " (leder)" in lower or lower.startswith("leder:"):
                    cand = clean_person_name(line)
                    if is_valid_person_name(cand):
                        leader = cand
                        mode = "in_members"
            elif mode == "in_members":
                if any(k in lower for k in ["sekretariatsleder", "sekretariat", "sekretærer", "(sekretariatsleder)", "(sekretær)"]):
                    cand, aff = extract_affiliations_from_line(line)
                    if is_valid_person_name(cand) and cand != leader:
                        secretariat.append(cand)
                        if aff:
                            affiliations_map[cand] = aff
                    mode = "in_secretariat"
                else:
                    cand, aff = extract_affiliations_from_line(line)
                    if is_valid_person_name(cand) and cand != leader and cand not in members:
                        members.append(cand)
                        if aff:
                            affiliations_map[cand] = aff
            elif mode == "in_secretariat":
                if any(k in lower for k in ["innhold", "kapittel", "del 1", "sammendrag"]):
                    break
                cand, aff = extract_affiliations_from_line(line)
                if is_valid_person_name(cand) and cand != leader and cand not in members and cand not in secretariat:
                    secretariat.append(cand)
                    if aff:
                        affiliations_map[cand] = aff

        if leader:
            result["leader"] = leader
            result["members"] = members
            result["secretariat"] = secretariat
            result["affiliations"] = [f"{person}: {org}" for person, org in affiliations_map.items()]
            result["confidence"] = 0.95 if (len(members) >= 2 or len(secretariat) >= 1) else 0.85

    except Exception as e:
        logger.warning(f"Failed to fetch regjeringen HTML for {url}: {e}")

    return result


def fetch_nb_api_creators(digibok_urn_or_id: str) -> list:
    """
    Queries `https://api.nb.no/catalog/v1/items?q=...` to retrieve authentic `metadata.creators`
    committee chair names for historical digitised books (`digibok_*`).
    """
    if not digibok_urn_or_id:
        return []

    clean_id = digibok_urn_or_id.strip()
    if not clean_id.startswith("URN:NBN:no-nb_"):
        if clean_id.startswith("digibok_"):
            urn = f"URN:NBN:no-nb_{clean_id}"
        elif re.match(r'^\d+$', clean_id):
            urn = f"URN:NBN:no-nb_digibok_{clean_id}"
        else:
            urn = clean_id
    else:
        urn = clean_id

    url = f"https://api.nb.no/catalog/v1/items?q={urn}"

    try:
        session = get_http_session()
        r = session.get(url, timeout=(5.0, 15.0))
        if r.status_code == 200:
            data = r.json()
            items = data.get("_embedded", {}).get("items", [])
            if items:
                metadata = items[0].get("metadata", {})
                raw_creators = metadata.get("creators", [])
                formatted = [format_creator_name(c) for c in raw_creators if c]
                valid_creators = [c for c in formatted if is_valid_person_name(c)]
                return valid_creators
    except Exception as e:
        logger.warning(f"Error querying NB API for {digibok_urn_or_id}: {e}")

    return []


def fetch_uio_duo_html(uio_url_or_id: str) -> dict:
    """
    Parses UiO Duo repository metadata for historical university NOUs.
    """
    result = {
        "leader": "",
        "members": [],
        "secretariat": [],
        "affiliations": [],
        "source": "uio_duo_html",
        "confidence": 0.0
    }

    if not uio_url_or_id:
        return result

    target = uio_url_or_id.strip()
    if target.startswith("http"):
        uio_url = target
    elif "/" in target:
        uio_url = f"https://www.duo.uio.no/handle/{target}"
    else:
        uio_url = f"https://www.duo.uio.no/handle/10852/{target}"

    try:
        session = get_http_session()
        r = session.get(uio_url, timeout=(5.0, 15.0))
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            authors = []
            for meta in soup.find_all("meta"):
                attr = meta.get("name", "").lower()
                if attr in ["dc.contributor.author", "dc.creator", "citation_author"]:
                    val = meta.get("content", "").strip()
                    if val and val not in authors:
                        authors.append(val)

            formatted = [format_creator_name(a) for a in authors if a]
            valid_authors = [a for a in formatted if is_valid_person_name(a)]

            if valid_authors:
                result["leader"] = valid_authors[0]
                result["members"] = valid_authors[1:]
                result["confidence"] = 0.80
    except Exception as e:
        logger.warning(f"Failed to fetch UiO Duo HTML for {uio_url_or_id}: {e}")

    return result


def scrape_nou_roster_html(nou_dict: dict) -> dict:
    """
    Orchestrates HTML-first sourcing based on NOU source URL / digibok ID, returning structured roster payload:
    {"nou_id": "...", "leader": "...", "members": [...], "secretariat": [...], "affiliations": [...], "source": "...", "confidence": float}
    """
    nou_id = str(nou_dict.get("nou_id") or nou_dict.get("id") or "").strip()
    source_url = str(nou_dict.get("source_url") or "").strip()
    pdf_url = str(nou_dict.get("pdf_url") or "").strip()

    payload = {
        "nou_id": nou_id,
        "leader": "",
        "members": [],
        "secretariat": [],
        "affiliations": [],
        "source": "unknown",
        "confidence": 0.0
    }

    # 1. Digibok / NB.no API check
    is_digibok = "digibok_" in nou_id or "digibok_" in pdf_url or "digibok_" in source_url or "nb.no" in pdf_url
    if is_digibok:
        digibok_key = nou_id
        if "digibok_" not in digibok_key:
            m = re.search(r'(digibok_\d+)', pdf_url + " " + source_url)
            if m:
                digibok_key = m.group(1)

        creators = fetch_nb_api_creators(digibok_key)
        if creators:
            payload["leader"] = creators[0]
            payload["members"] = creators[1:]
            payload["source"] = "nb_api_creators"
            payload["confidence"] = 0.85
            return payload

    # 2. UiO Duo check
    is_uio = nou_id.startswith("uio_") or "duo.uio.no" in source_url
    if is_uio:
        uio_res = fetch_uio_duo_html(source_url or nou_id)
        if uio_res.get("leader"):
            payload["leader"] = uio_res["leader"]
            payload["members"] = uio_res.get("members", [])
            payload["source"] = "uio_duo_html"
            payload["confidence"] = uio_res.get("confidence", 0.80)
            return payload

    # 3. Regjeringen HTML check
    target_regjeringen_url = source_url
    if not target_regjeringen_url and re.match(r'^(id)?\d+$', nou_id):
        target_regjeringen_url = nou_id

    if target_regjeringen_url or "regjeringen.no" in source_url:
        reg_res = fetch_regjeringen_ch1_html(target_regjeringen_url or source_url)
        if reg_res.get("leader"):
            payload["leader"] = reg_res["leader"]
            payload["members"] = reg_res.get("members", [])
            payload["secretariat"] = reg_res.get("secretariat", [])
            payload["affiliations"] = reg_res.get("affiliations", [])
            payload["source"] = "regjeringen_html"
            payload["confidence"] = reg_res.get("confidence", 0.95)
            return payload

    return payload


if __name__ == "__main__":
    print("=" * 70)
    print("M2 HTML-First Scraper Test Runner")
    print("=" * 70)

    test_cases = [
        {"id": "3167083", "title": "NOU 2026: 8 - Samarbeid og informasjonsdeling for å forebygge kriminalitet", "source_url": "https://www.regjeringen.no/no/dokumenter/id3167083/"},
        {"id": "3145481", "title": "NOU 2026: 1 - En bærekraftig kommunesektor", "source_url": "https://www.regjeringen.no/no/dokumenter/id3145481/"},
        {"id": "digibok_2017112907505", "title": "NOU 1976: Sluttrapport", "pdf_url": "https://www.nb.no/items/URN:NBN:no-nb_digibok_2017112907505"},
        {"id": "digibok_2007082304052", "title": "NOU 1991: Miljøsikkerhet i innseilingsleder", "pdf_url": "https://www.nb.no/items/URN:NBN:no-nb_digibok_2007082304052"},
    ]

    for test_item in test_cases:
        logger.info(f"Testing extraction for NOU ID: {test_item['id']}")
        res = scrape_nou_roster_html(test_item)
        print(f"\nResult for {test_item['id']} ({test_item['title']}):")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        print("-" * 50)
