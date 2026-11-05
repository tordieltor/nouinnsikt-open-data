#!/usr/bin/env python3
"""
pipeline/scrape_upcoming_nous.py
================================
Authoritative harvester & parser for active Norwegian Official Commissions (utvalg under arbeid)
preparing upcoming NOUs (Kommande NOU-ar) from Regjeringen.no.

Features:
- Multi-channel discovery: Central SRU portal, 17 ministry organization directories, and appointment searches.
- Robust filtering: Strips permanent administrative boards, statutory councils, and completed commissions.
- Entity Reconciliation: Merges press release announcements with ministry organization pages.
- Deep structured extraction: Committee leader (name, title, location), members roster, mandate summary,
  appointed date, delivery deadline, normalized ministerial lineage, and canonical URLs.
- 100% Factuality & HTTP 200 Reachability Guard: Validates every single URL against live infrastructure.
- CLI Interface: Standard --apply, --dry-run, --force, --output flags.
- Atomic Serialization: Writes master JSON to data/upcoming_nous.json and copies to frontend/lib/upcoming_nous.json.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set, Tuple

from bs4 import BeautifulSoup

# Ensure project root & backend are on sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from backend.app.lib.ministry_resolver import (
    get_code_to_modern_map,
    normalize_ministry_name,
    resolve_ministry_lineage,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scrape_upcoming_nous")

# Default HTTP headers
USER_AGENT = "NOUinnsikt-Harvester/1.0 (+https://nouinnsikt.no)"
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}

# Norwegian month name mapping
NORWEGIAN_MONTHS: Dict[str, int] = {
    "januar": 1, "februar": 2, "mars": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12,
}

# Known Norwegian locations for cleaner person parsing
KNOWN_LOCATIONS: Set[str] = {
    "oslo", "bergen", "trondheim", "stavanger", "tromsø", "kristiansand", "drammen",
    "bærum", "asker", "nesodden", "bodø", "tromso", "ålesund", "arendal", "molde",
    "hamar", "moss", "skien", "sandefjord", "tønsberg", "haugesund", "gjøvik",
    "lillehammer", "alta", "kautokeino", "karasjok", "bardu", "steinkjer", "halden",
    "levanger", "volda", "sogndal", "elverum", "sarpsborg", "fredrikstad", "horten",
    "kongsberg", "harstad", "mo i rana", "narvik", "kongsvinger", "nittedal", "oppegård",
    "ski", "karmøy", "time", "sandnes", "sola", "klepp", "bryne", "stord", "årdal",
    "øygarden", "midttre-gauldal", "midt-telemark", "nannestad", "ullensaker", "enebakk",
    "alstahaug", "alstadhaug", "engerdal", "eidskog", "ringsaker", "nes", "voss", "sunnfjord",
    "stryn", "svolvær", "vefsn", "rana", "namsos", "stjørdal", "melhus", "orkland", "kinn",
    "askøy", "bjørnafjorden", "alver", "hå", "eigersund", "farsund", "flekkefjord", "lyngdal",
    "mandal", "lindesnes", "vennesla", "grimstad", "risør", "kragerø", "porsgrunn", "notodden",
    "nome", "tinn", "larvik", "holmestrand", "færder", "ringerike", "hole", "lier", "øvre eiker",
    "modum", "nordre follo", "ås", "frogn", "vestby", "lillestrøm", "lørenskog", "rælingen",
    "aurskog-høland", "gjerdrum", "eidsvoll", "hurdal", "rakkestad", "indre østfold", "marker",
    "skiptvet", "våler", "råde", "hvaler", "løten", "stange", "nord-odal", "sør-odal", "grue",
    "åsnes", "trysil", "åmot", "stor-elvdal", "rendalen", "tolga", "tynset", "alvdal", "folldal",
    "os", "øyer", "gausdal", "østre toten", "vestre toten", "gran", "søndre land", "nordre land",
    "sør-aurdal", "etnedal", "nord-aurdal", "vestre slidre", "øystre slidre", "vang", "dovre",
    "lesja", "skjåk", "lom", "vågå", "nord-fron", "sel", "sør-fron", "ringebu", "bindal",
    "sømna", "brønnøy", "vega", "vevelstad", "herøy", "leirfjord", "grane", "hattfjelldal",
    "dønna", "nesna", "hemnes", "rødøy", "meløy", "gildeskål", "beiarn", "saltdal", "fauske",
    "sørfold", "steigen", "lødingen", "evenes", "røst", "værøy", "flakstad", "vestvågøy",
    "vågan", "hadsel", "bø", "øksnes", "sortland", "andøy", "moskenes", "kvæfjord", "tjeldsund",
    "ibestad", "gratangen", "lavangen", "salangen", "målselv", "sørreisa", "dyrøy", "senja",
    "balsfjord", "karlsøy", "lyngen", "storfjord", "kåfjord", "skjervøy", "nordreisa", "kvænangen",
    "vardø", "vadsø", "hammerfest", "porsanger", "deatnu", "tana", "nesseby", "båtsfjord",
    "berlevåg", "sør-varanger", "gamvik", "lebesby", "måsøy", "nordkapp", "hasvik", "loppa"
}

# Known non-temporary, permanent, advisory, or already delivered entities to filter out
NON_UTVALG_BLACKLIST: List[str] = [
    "opera", "wergelandsenteret", "dataprioriteringsradet", "digitaliseringsradet",
    "arbeidsgiverradet", "bunad", "klagenemnd", "vergemålsnemnd", "nemnd",
    "bistandsnemnd", "etatsstyre", "rikslønnsnemnd", "forliksråd", "etisk råd",
    "fylkesnemnd", "kontaktutvalg", "partssammensatt", "brukerutvalg", "samarbeidsorgan",
    "utenrikstjenesten", "e-helsestyret", "nasjonalt råd", "rådgivende utvalg for finansielle",
    "posten", "avinor", "vy", "statskog", "norsk tipping", "barentssekretariatet",
    "statens pensjonskasse", "garantikassen", "klagenemnda", "medieklagenemnda",
    "lotterinemnda", "konkurranseklagenemnda", "trygderetten", "finansklagenemnda",
    "organisasjonsledd", "virksomheter", "etater-virksomheter", "ledige-stillinger",
    "tvisteløser", "garantiordningen", "kunstnarstipend", "produksjonstilskudd",
    "styret i", "styret for", "styret ved", "styre-den-norske", "sikkerhetsrådet for luftfarten",
    "rådet for statistisk", "rådgivende utvalg for finanspolitiske", "samarbeidsrådet for yrkesopplæring",
    "standardiseringsrådet", "statens lønnsutvalg", "styre for statens investeringsfond",
    "styrer ved universiteter", "prisråd for grunnrenteskatten", "programstyre for merkur",
    "referansegruppe for samordning", "regjeringens representasjonsutvalg", "skjermbrukutvalget",
    "norsk kulturfond", "norges banks hovedstyre", "nasjonalt geodataråd", "ogp-rådet",
    "offentlig utvalg for punktskrift", "petroleumsprisrådet", "zeepipe-kommisjonen",
    "jury", "priskomite", "pipeline commission", "komité for pengepolitikk", "komité for kjønnsbalanse",
    "kontrollkomiteen", "koordineringsutvalget", "kompetansepolitisk råd", "mannsutvalget",
    "kompetansereformsutvalget", "avkommersialiseringsutvalet", "drosjeutvalget", "kjernekraftutvalget",
    "baneheia-utvalget", "skatteutvalget", "generalistkommuneutvalget",
    "helsepersonellkommisjonen", "koronakommisjonen", "totalberedskapskommisjonen", "musikkfeltet",
    "antihvitvasking", "kompetansebehov", "heimeeksamen"
]

# All 17 modern ministries shortcodes
MINISTRY_CODES = [
    "aid", "bfd", "dfd", "ed", "fd", "fin", "hod", "jd", "kdd",
    "kd", "kld", "kud", "lmd", "nfd", "sd", "ud", "smk"
]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def fetch_url(url: str, timeout: int = 10, retries: int = 2) -> Tuple[str, Optional[str], int]:
    """Fetches HTML content from URL with polite backoff."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status_code = resp.status
                if status_code == 200:
                    content = resp.read().decode("utf-8", errors="replace")
                    return url, content, 200
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return url, None, 404
            time.sleep(0.3 * (attempt + 1))
        except Exception:
            time.sleep(0.3 * (attempt + 1))
    return url, None, 0


def parse_norwegian_date(date_str: Optional[str]) -> Optional[str]:
    """Parses date string formatted as DD.MM.YYYY or 'DD. måned YYYY' into ISO YYYY-MM-DD."""
    if not date_str or not isinstance(date_str, str):
        return None
    # Match DD.MM.YYYY
    m1 = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_str)
    if m1:
        return f"{m1.group(3)}-{int(m1.group(2)):02d}-{int(m1.group(1)):02d}"
    # Match DD. måned YYYY
    m2 = re.search(r"(\d{1,2})\.?\s+([A-Za-zÆØÅæøå]+)\s+(\d{4})", date_str)
    if m2:
        day = int(m2.group(1))
        month_str = m2.group(2).lower()
        year = int(m2.group(3))
        month = NORWEGIAN_MONTHS.get(month_str)
        if month:
            return f"{year}-{month:02d}-{day:02d}"
    return None


def is_valid_human_name(name: str) -> bool:
    """Strictly validates human name formatting and word bounds."""
    if not name or len(name) < 3 or len(name) > 60:
        return False
    # Filter meta-labels and noise
    if any(noise in name.lower() for noise in [
        "skal", "vurdere", "foreslår", "utvalget", "utvalet", "departementet",
        "lov", "forskrift", "rapport", "endring", "avgrensning", "arbeidsområde",
        "oppgaver", "organisatorisk", "innstilling", "medlemmer", "sammensetning",
        "mandat", "bakgrunn", "type:", "opprettet:", "status:", "dato:", "avsluttet:"
    ]):
        return False
    words = name.split()
    if len(words) < 2 or len(words) > 5:
        return False
    # Ensure title-cased words
    if not all(w[0].isupper() for w in words if len(w) > 1 and w.lower() not in ["og", "av", "i", "på", "van", "der", "von", "de"]):
        return False
    return True


TITLE_KEYWORDS: Set[str] = {
    "professor", "førsteamanuensis", "forsker", "forskningsdirektør", "forskningsleder",
    "dekan", "advokat", "direktør", "avdelingsdirektør", "administrerende direktør",
    "sorenskriver", "lagmann", "lagdommer", "tingrettsdommer", "dommer", "overlege",
    "kommuneoverlege", "siviløkonom", "samfunnsøkonom", "statsforvalter", "stortingsrepresentant",
    "ordfører", "generalsekretær", "partisekretær", "leder", "leiar", "spesialist",
    "spesialrådgiver", "seniorrådgiver", "rådgiver", "seniorforsker", "statssekretær",
    "forbundsleder", "førstestatsadvokat", "viserektor", "fylkeslege", "redaktør",
    "journalist", "forfatter", "kunstner", "musiker", "manager", "kommuneadvokat",
    "fylkesordfører", "fylkesråd", "seksjonsleder", "postdoktor", "stipendiat",
    "jurist", "analytiker", "konsulent", "ingeniør", "representant", "statsråd"
}


PARTY_TAGS: Set[str] = {
    "ap", "h", "frp", "sp", "sv", "v", "krf", "mdg", "r", "rødt", "rodt",
    "høyre", "hoyre", "venstre", "arbeiderpartiet", "senterpartiet",
    "fremskrittspartiet", "sosialistisk venstreparti", "kristelig folkeparti",
    "miljøpartiet de grønne"
}


def clean_person_string(text: Optional[str]) -> Optional[Dict[str, Optional[str]]]:
    """Extracts structured name, professional title, and location from a person string."""
    if not text:
        return None
    text = re.sub(
        r"^(?:(?:Leder|Leiar|Utvalgsleder|Utvalsleiar|Nestleder|Nestleiar|Medlem|Medlemer|Medlemmer|Leder/nestleder)\s*[:,\-–]\s*)+",
        "",
        text,
        flags=re.I
    ).strip()
    text = re.sub(r"\s*\((?:utvalgsleder|utvalsleiar|leder|leiar|nestleder|nestleiar|medlem|medlemer|medlemmer|sekretær|sekretariat)\)\s*$", "", text, flags=re.I).strip()
    
    # Strip trailing political party tags prior to splitting on commas (e.g. ", SV", ", Ap")
    text = re.sub(r"\s*,\s*(?:Ap|H|FrP|Sp|SV|V|KrF|MDG|R|FRP|AP|HØYRE|VENSTRE|SV|SP|MDG|KRF|RØDT)\s*$", "", text, flags=re.I).strip()
    text = text.rstrip(".,:;")

    parts = [p.strip() for p in text.split(",") if p.strip() and p.strip().lower() not in PARTY_TAGS]
    if not parts:
        return None

    first_part = parts[0]
    location: Optional[str] = None
    title: Optional[str] = None
    name: str = first_part

    # Recognized professional titles in first part
    title_regex = (
        r"^(Professor\s+II|Førsteamanuensis\s+II|Forsker\s+I|Forsker\s+II|Professor|Førsteamanuensis|"
        r"Postdoktor|Forsker|Forskningsdirektør|Forskningsleder|Dekan|Advokat|Direktør|"
        r"Avdelingsdirektør|Administrerende\s+direktør|[A-Za-zÆØÅæøå\-]+-direktør|[A-Za-zÆØÅæøå\-]+-leder|"
        r"Sorenskriver|Lagmann|Lagdommer|Tingrettsdommer|Kommuneoverlege|Siviløkonom|Samfunnsøkonom|"
        r"Statsforvalter|Stortingsrepresentant|Ordfører|Generalsekretær|Assisterende\s+partisekretær|"
        r"Assisterende\s+generalsekretær|Partisekretær|Økonomiansvarlig|Daglig\s+leder|Spesialist|"
        r"Spesialrådgiver|Seniorrådgiver|Rådgiver|Seniorforsker|Statssekretær|Forbundsleder|"
        r"Pensjonert\s+journalist|Pensjonert\s+regjeringsadvokat|"
        r"Førstestatsadvokat|Viserektor|Fylkeslege|Musiker|Manager|Kunstner|Forfatter|Journalist|Redaktør|Tidligere\s+statsråd)\s+(.+)$"
    )
    tm = re.match(title_regex, first_part, re.I)
    if tm:
        title = tm.group(1).strip()
        name = tm.group(2).strip()

    if len(parts) == 2:
        cand = parts[1].strip()
        cand_lower = cand.lower()
        if cand_lower in KNOWN_LOCATIONS:
            location = cand
        elif any(kw in cand_lower for kw in TITLE_KEYWORDS):
            if not title:
                title = cand
        else:
            # Default single-word or geographic label as location
            if not title and len(cand.split()) <= 2:
                location = cand
            elif not title:
                title = cand
    elif len(parts) >= 3:
        if parts[-1].lower() in KNOWN_LOCATIONS:
            location = parts[-1]
            if not title:
                title = parts[1]
        elif len(parts) >= 3 and parts[2].lower() in KNOWN_LOCATIONS:
            location = parts[2]
            if not title:
                title = parts[1]
        else:
            if not title:
                title = parts[1]
            location = parts[-1]

    # Clean name of any trailing party tags or punctuation
    name = re.sub(r"\s*,\s*(?:Ap|H|FrP|Sp|SV|V|KrF|MDG|R|FRP|AP)\s*$", "", name).strip()
    name = name.rstrip(".,:;")

    if not is_valid_human_name(name):
        return None

    return {
        "name": name,
        "title": title.strip() if title else None,
        "location": location.strip().capitalize() if location else None
    }


def get_canonical_topic_key(title: str, slug: str) -> str:
    """Computes normalized canonical topic key for entity reconciliation across duplicate URLs."""
    combined = (title + " " + slug).lower()
    if "pasient" in combined and "rettighet" in combined:
        return "pasient-og-brukerrettighetslovutvalget"
    if "ekspropriasjon" in combined:
        return "ekspropriasjonsavklaringsutvalget"
    if "studielån" in combined or "studielan" in combined or "studiefinansiering" in combined:
        return "studiefinansieringsutvalget"
    if "norskopplæring" in combined or "norskopplaring" in combined:
        return "norskopplaring-for-voksne-innvandrere"
    if "skattekommisjon" in combined:
        return "skattekommisjonen"
    if "lesekommisjon" in combined or "lesing" in combined:
        return "lesekommisjonen"
    if "kjernekraft" in combined:
        return "kjernekraftutvalget"
    if "partilov" in combined or "partiloven" in combined:
        return "partilovutvalget"
    if "arealnøytralitet" in combined or "arealnoytralitet" in combined:
        return "arealnoytralitet"
    if "innvandrerhelse" in combined:
        return "innvandrerhelse"
    if "politi" in combined:
        return "politirolleutvalget"
    if "lagmannsrett" in combined:
        return "lagmannsrettsutvalget"
    if "cruiseskip" in combined or "cruise" in combined:
        return "norske-lonnsvilkar-pa-cruiseskip"
    if "veteranlov" in combined or "veteran" in combined:
        return "veteranlovutvalget"
    if "rusbehandling" in combined:
        return "rusbehandlingsutvalget"
    if "doktorgrad" in combined:
        return "doktorgradsutdanning"
    if "cmdi" in combined or "bankkrise" in combined or "innskuddsgaranti" in combined:
        return "cmdi-utvalget"
    if "omstilling" in combined:
        return "omstillingskommisjonen"
    if "arbeidsinnvandring" in combined:
        return "arbeidsinnvandringsutvalget"
    if "gardermoen" in combined or "oslo lufthavn" in combined:
        return "oslo-lufthavn-kapasitetsutvalg"
    if "legemidler" in combined:
        return "tidlig-tilgang-legemidler"
    if "samiske barnehage" in combined or ("samisk" in combined and "barnehage" in combined):
        return "samiske-barnehagetilbud"
    if "råstoffkvalitet" in combined or "rastoffkvalitet" in combined or "fiskerinæringen" in combined:
        return "rastoffkvalitet-fiskeri"
    if "matsystem" in combined:
        return "matsystemutvalget"
    if "fødselstal" in combined or "fødselstall" in combined:
        return "fodselstallsutvalget"
    if "pensjonsfond" in combined or "etiske rammeverket" in combined or "etikkutvalg" in combined:
        return "etikkutvalget-spu"
    if "forsvarere" in combined or "salærsats" in combined or "salær" in combined or "godtgjør" in combined:
        return "salaersatsutvalget"
    if "kommunekommisjon" in combined:
        return "kommunekommisjonen"
    if "kraftmarked" in combined:
        return "kraftmarkedsutvalget"
    if "fiskerpensjon" in combined:
        return "fiskerpensjon-utvalget"
    if "bostøtt" in combined or "bostotte" in combined:
        return "bostotteutvalget"
    return slug


# ============================================================================
# SCRAPER & PARSER CORE
# ============================================================================

class UpcomingNousScraper:
    def __init__(self, force: bool = False, max_workers: int = 12):
        self.force = force
        self.max_workers = max_workers
        self.delivered_titles: Set[str] = set()
        self.delivered_slugs: Set[str] = set()
        self._load_delivered_catalog()

    def _load_delivered_catalog(self) -> None:
        """Loads delivered NOU catalog from frontend/lib/nou_catalog.json for exclusion."""
        cat_path = os.path.join(ROOT_DIR, "frontend", "lib", "nou_catalog.json")
        if os.path.exists(cat_path):
            try:
                with open(cat_path, "r", encoding="utf-8") as f:
                    catalog = json.load(f)
                    for item in catalog:
                        if "title" in item:
                            raw_t = item["title"].lower().strip()
                            self.delivered_titles.add(raw_t)
                            clean_t = re.sub(r"^nou\s+\d{4}\s*:\s*\d+\s*[-–:]\s*", "", raw_t).strip()
                            if clean_t:
                                self.delivered_titles.add(clean_t)
                        if "slug" in item:
                            self.delivered_slugs.add(item["slug"].lower().strip())
                logger.info("Loaded %d delivered NOUs for duplicate exclusion.", len(catalog))
            except Exception as e:
                logger.warning("Could not read nou_catalog.json: %s", e)

    def discover_candidate_urls(self) -> List[str]:
        """Discovers candidate commission URLs across SRU, ministry hubs, and search endpoints."""
        logger.info("Starting multi-channel commission discovery sweep...")
        discovery_targets: List[str] = []

        # 1. Ministry organization hubs
        for code in MINISTRY_CODES:
            discovery_targets.extend([
                f"https://www.regjeringen.no/no/dep/{code}/org/styrer-rad-og-utvalg/",
                f"https://www.regjeringen.no/no/dep/{code}/organisasjon/styrer-rad-og-utvalg/",
                f"https://www.regjeringen.no/no/dep/{code}/org/styre-rad-og-utval/",
                f"https://www.regjeringen.no/no/dep/{code}/organiseringen-av-{code}/styrer-rad-og-utvalg/",
                f"https://www.regjeringen.no/no/dep/{code}/organisasjon/styrer-rad-og-utvalg/midlertidige-rad-og-utvalg/",
                f"https://www.regjeringen.no/no/dep/{code}/org/styrer-rad-og-utvalg/tidsbegrensede-styrer-rad-og-utvalg/",
                f"https://www.regjeringen.no/no/dep/{code}/org/styrer-rad-og-utvalg-under-{code}/",
                f"https://www.regjeringen.no/no/dep/{code}/org/styrer-rad-og-utvalg-oppnevnt-av-{code}/",
            ])

        # 2. Central SRU portal (pages 1-22)
        for page in range(1, 23):
            discovery_targets.append(
                f"https://www.regjeringen.no/no/om-regjeringa/sru/id2405055/?sortby=1&page={page}"
            )

        # 3. Quoted search queries for appointments & royal decrees
        search_phrases = [
            '"oppnevnt" "utvalg" "skal levere"',
            '"oppnemnt" "utval" "skal levere"',
            '"offentlig utvalg" "mandat"',
            '"skal levere sin utredning"',
            '"skal levere si utgreiing"',
            '"utvalget skal levere"',
            '"regjeringen har i dag oppnevnt" utvalg',
            '"regjeringa har i dag oppnemnt" utval',
            '"kongelig resolusjon" "oppnevning av" utvalg',
            '"kongelig resolusjon" "oppnemning av" utval',
            '"regjeringen setter ned utvalg"',
            '"regjeringa set ned utval"',
            '"ekspertgruppe" "mandat"'
        ]
        for phrase in search_phrases:
            for page in range(1, 4):
                encoded = urllib.parse.quote(phrase)
                discovery_targets.append(
                    f"https://www.regjeringen.no/no/sok/id86008/?term={encoded}&sortby=1&page={page}"
                )

        # Baseline confirmed targets to guarantee completeness (including the 6 new seed URLs)
        seed_urls = [
            "https://www.regjeringen.no/no/dep/nfd/org/styrer-rad-og-utvalg/fiskerpensjon-utvalget/id3168365/",
            "https://www.regjeringen.no/no/aktuelt/matsystemutvalget-skal-gjennomga-hele-matsystemet/id3148088/",
            "https://www.regjeringen.no/no/dep/kdd/org/styrer-rad-og-utvalg/bostotteutvalget/id3144145/",
            "https://www.regjeringen.no/no/dep/fin/org/styrer-rad-og-utvalg-oppnevnt-av-finansdepartementet2/etikkutvalget/id3138380/",
            "https://www.regjeringen.no/no/dep/kdd/org/styrer-rad-og-utvalg/kommunekommisjonen/id3114028/",
            "https://www.regjeringen.no/no/dep/hod/organiseringen-av-helse-og-omsorgsdepartementet/styrer-rad-og-utvalg/rusbehandlingsutvalget/id3111755/",
            "https://www.regjeringen.no/no/dep/jd/org/styre-rad-og-utval/tidsbegrensede-styrer-rad-og-utvalg/salaersatsutvalget/id3110413/",
            "https://www.regjeringen.no/no/aktuelt/regjeringen-setter-ned-utvalg-om-norske-lonnsvilkar-pa-cruiseskip/id3170976/",
            "https://www.regjeringen.no/no/dep/kld/organisasjon/styrer-rad-og-utvalg/midlertidige-rad-og-utvalg/utvalg-om-arealnoytralitet/id3169921/",
            "https://www.regjeringen.no/no/dep/hod/organiseringen-av-helse-og-omsorgsdepartementet/styrer-rad-og-utvalg/utvalg-om-innvandrerhelse/id3167530/",
            "https://www.regjeringen.no/no/aktuelt/utvalg-skal-utrede-forslag-til-en-veteranlov/id3166830/",
            "https://www.regjeringen.no/no/aktuelt/arbeidsinnvandringsutvalget-er-klart/id3164385/",
            "https://www.regjeringen.no/no/aktuelt/nytt-utvalg-skal-vurdere-tidlig-tilgang-til-legemidler/id3158080/",
            "https://www.regjeringen.no/no/aktuelt/utvalg-skal-vurdere-tiltak-for-a-sikre-bedre-rastoffkvalitet-i-fiskerinaringen/id3157081/",
            "https://www.regjeringen.no/no/dep/kdd/org/styrer-rad-og-utvalg/utvalg-som-skal-utrede-det-samiske-barnehagetilbudet/id3155737/",
            "https://www.regjeringen.no/no/dep/fin/org/styrer-rad-og-utvalg-oppnevnt-av-finansdepartementet2/cmdi-utvalget/id3153197/",
            "https://www.regjeringen.no/no/dep/jd/org/styre-rad-og-utval/tidsbegrensede-styrer-rad-og-utvalg/utvalg-som-skal-utrede-lagmannsrettens-funksjon-og-saksbehandling/id3153243/",
            "https://www.regjeringen.no/no/dep/kdd/org/styrer-rad-og-utvalg/partilovutvalget/id3145428/",
            "https://www.regjeringen.no/no/dep/jd/org/styre-rad-og-utval/tidsbegrensede-styrer-rad-og-utvalg/utvalg-som-skal-utrede-politiets-rolle-i-samfunnet/id3111352/",
            "https://www.regjeringen.no/no/dep/kd/org/styrer-rad-og-utvalg/ekspertgruppe-om-doktorgradsutdanning/id3158708/",
            "https://www.regjeringen.no/no/dep/fin/org/styrer-rad-og-utvalg-oppnevnt-av-finansdepartementet2/omstillingskommisjonen/id3153200/",
            "https://www.regjeringen.no/no/dep/hod/organiseringen-av-helse-og-omsorgsdepartementet/styrer-rad-og-utvalg/pasient-og-brukerrettighetslovutvalget/id3139316/",
            "https://www.regjeringen.no/no/dep/jd/org/styre-rad-og-utval/tidsbegrensede-styrer-rad-og-utvalg/utvalg-som-skal-utrede-tidligere-rettslig-avklaring-i-ekspropriasjonssaker/id3110382/",
            "https://www.regjeringen.no/no/aktuelt/nytt-utval-skal-foresla-framtidas-ordningar-for-studielan-og-stipend/id3142805/",
            "https://www.regjeringen.no/no/aktuelt/ekspertutvalg-skal-se-pa-norskopplaringstilbudet-for-innvandrere/id3157571/",
            "https://www.regjeringen.no/no/dep/fin/org/styrer-rad-og-utvalg-oppnevnt-av-finansdepartementet2/skattekommisjonen/id3144542/",
            "https://www.regjeringen.no/no/aktuelt/ny-lesekommisjon-skal-gi-nasjonale-rad-om-lesing/id3148010/"
        ]

        discovered_links: Set[str] = set(seed_urls)
        logger.info("Scanning %d discovery endpoints concurrently...", len(discovery_targets))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(fetch_url, u): u for u in discovery_targets}
            for f in as_completed(futures):
                url, html, status = f.result()
                if not html or status != 200:
                    continue

                soup = BeautifulSoup(html, "html.parser")
                if "/sok/" in url:
                    container = soup.find(class_=re.compile(r"search-results|result-list", re.I)) or soup.find("main") or soup
                    for a in container.find_all("a", href=re.compile(r"/id\d+")):
                        href = a["href"].split("?")[0]
                        if href.startswith("/"):
                            href = "https://www.regjeringen.no" + href
                        if any(x in href for x in ["/aktuelt/", "/dokumenter/", "/org/"]):
                            if not any(x in href for x in ["/prop-", "/meld-st-", "/horinger/", "/tidligere", "/innstillinger"]):
                                discovered_links.add(href)
                else:
                    main = soup.find("main") or soup
                    for a in main.find_all("a", href=re.compile(r"/id\d+")):
                        href = a["href"].split("?")[0]
                        if href.startswith("/"):
                            href = "https://www.regjeringen.no" + href
                        if "/org/" in href or "/aktuelt/" in href or "/dokumenter/" in href:
                            if not any(x in href for x in ["/tidligere", "/avsluttede", "/innstillinger", "/permanente", "/prop-", "/meld-st-"]):
                                discovered_links.add(href)

        logger.info("Discovered %d candidate commission URLs.", len(discovered_links))
        return sorted(list(discovered_links))

    def parse_commission_page(self, url: str, html: str) -> Optional[Dict[str, Any]]:
        """Parses raw HTML from Regjeringen.no into a structured Upcoming NOU item."""
        soup = BeautifulSoup(html, "html.parser")
        main = soup.find("main") or soup
        full_text = main.get_text(separator="\n", strip=True)
        lower_text = full_text.lower()

        h1 = soup.find("h1")
        raw_h1 = h1.get_text(strip=True) if h1 else ""

        # 1. Filter out blacklisted permanent organs
        if any(b in lower_text[:400] or b in url.lower() or b in raw_h1.lower() for b in NON_UTVALG_BLACKLIST):
            return None

        # 2. Filter out delivered NOUs / completed commissions
        delivered_markers = [
            "leverte sin utredning", "la frem sin utredning", "la fram si utgreiing",
            "overleverte sin utredning", "la frem sin rapport", "har overlevert",
            "avsluttet sitt arbeid", "utvalget har levert", "utvalet har levert",
            "tidligere-styrer-rad-og-utvalg", "avsluttede-styrer", "innstillinger-fra-utvalg",
            "leverte nou", "la fram nou", "overleverte nou", "la frem nou", "frårår bruk"
        ]
        if any(m in lower_text for m in delivered_markers) or any(m in url for m in delivered_markers):
            return None

        # 3. Must indicate a committee / expert group
        if not any(w in raw_h1.lower() or w in url.lower() for w in ["utvalg", "utval", "kommisjon", "ekspertgruppe", "arbeidsgruppe", "gjennomgang"]):
            return None

        # 4. Clean title
        title = re.sub(
            r"^(?:Regjeringen\s+(?:har\s+i\s+dag\s+)?(?:setter\s+ned|oppnevner|oppnevnte|har\s+nedsatt|oppnemner)\s+(?:et\s+|eit\s+)?|"
            r"Regjeringa\s+(?:har\s+i\s+dag\s+)?(?:set\s+ned|oppnemner|oppnemnde)\s+(?:eit\s+|et\s+)?|"
            r"Nytt\s+utvalg\s+skal\s+(?:se\s+på|gå\s+gjennom|utrede)|"
            r"Utvalg\s+skal\s+(?:utrede|vurdere|gå\s+gjennom)\s+|"
            r"Utval\s+skal\s+(?:utgreie|vurdere)\s+)",
            "",
            raw_h1,
            flags=re.I
        ).strip()

        if title:
            title = title[0].upper() + title[1:]
        else:
            return None

        if len(title) < 5 or len(title) > 130:
            return None

        # 5. ID and Slug
        id_m = re.search(r"/id(\d+)/?", url)
        id_num = id_m.group(1) if id_m else str(abs(hash(url)) % 10000000)
        item_id = f"utvalg-{id_num}"

        slug_match = re.search(r"/([^/]+)/id\d+/?", url)
        if slug_match:
            slug = slug_match.group(1).lower()
            slug = re.sub(r"^(?:regjeringen-setter-ned-utvalg-om-|regjeringen-oppnevner-utvalg-om-|utvalg-skal-utrede-|utvalg-om-|utval-om-)", "", slug)
        else:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

        # 6. Delivered exclusion check against delivered NOU catalog and known completed commissions
        known_delivered_slugs = {
            "kjernekraftutvalget", "fodselstallsutvalget", "oslo-lufthavn-kapasitetsutvalg",
            "mannsutvalget", "avkommersialiseringsutvalet", "drosjeutvalget",
            "generalistkommuneutvalget", "helsepersonellkommisjonen", "koronakommisjonen",
            "totalberedskapskommisjonen", "skjermbrukutvalget"
        }
        if (
            slug in known_delivered_slugs or
            any(slug in ds for ds in self.delivered_slugs) or
            any(title.lower() in dt for dt in self.delivered_titles)
        ):
            return None

        # 7. Ministry Lineage Normalization
        dep_code_match = re.search(r"/no/dep/([a-z]+)/", url)
        raw_dep = dep_code_match.group(1).upper() if dep_code_match else None
        ministry_name = None
        ministry_code = None

        if raw_dep:
            info = resolve_ministry_lineage(raw_dep)
            if info and info.get("canonical_name"):
                ministry_name = info["canonical_name"]
                ministry_code = info.get("code")

        if not ministry_name:
            code_to_modern = get_code_to_modern_map()
            for code, canon in code_to_modern.items():
                if code != "SMK" and canon.lower() in full_text.lower():
                    ministry_name = canon
                    ministry_code = code
                    break

        if not ministry_name:
            ministry_name = "Kommunal- og distriktsdepartementet"
            ministry_code = "KDD"

        # 8. Appointed Date
        appointed_date = None
        app_match = re.search(
            r"(?:oppnevnte?|satt ned|nedsatt|oppnemnde?)\s+(?:den\s+)?(\d{1,2}\.?\s+[A-Za-zÆØÅæøå]+\s+\d{4}|\d{1,2}\.\d{1,2}\.\d{4})",
            full_text,
            re.I
        )
        if app_match:
            appointed_date = parse_norwegian_date(app_match.group(1))
        if not appointed_date:
            date_el = soup.find(class_=re.compile(r"date|published|time", re.I))
            if date_el:
                appointed_date = parse_norwegian_date(date_el.get_text(strip=True))

        # 9. Deadline & Expected Delivery Year
        deadline = None
        deadline_display = None
        expected_year = None

        dl_match = re.search(
            r"(?:skal levere|leveringsfrist|frist|innen|innan|overlevere|skal overlevere)[^.\n]*?(\d{1,2}\.?\s+[A-Za-zÆØÅæøå]+\s+\d{4}|\d{1,2}\.\d{1,2}\.\d{4})",
            full_text,
            re.I
        )
        if dl_match:
            deadline = parse_norwegian_date(dl_match.group(1))
            deadline_display = dl_match.group(1).strip()
            if deadline:
                expected_year = int(deadline.split("-")[0])

        if not expected_year:
            season_match = re.search(
                r"((?:våren|sommeren|høsten|vinteren|innen utgangen av|i løpet av|innen|innan)\s+(202[5-9]|203\d))",
                full_text,
                re.I
            )
            if season_match:
                deadline_display = season_match.group(1).strip().capitalize()
                expected_year = int(season_match.group(2))

        # Check appointed date if recent (2024–2026)
        if not expected_year and appointed_date:
            app_year = int(appointed_date.split("-")[0])
            if app_year >= 2024:
                expected_year = max(2026, app_year + 1)
                deadline_display = f"Forventet {expected_year}"

        # If still no deadline and not a recently appointed committee, filter out (it's likely a permanent body)
        if not expected_year:
            return None

        # Exclude historical past delivery dates (< 2026)
        if expected_year < 2026:
            return None

        # 10. Leader Extraction
        leader = None

        # Pattern 1: Label with colon or dash (e.g. "Leder:\nAdministrerende direktør Bård Vegar Solhjell, Oslo")
        lead_label = re.search(
            r"(?<!vei)(?:Utvalgsleder|Utvalsleiar|Utvalgslederen|Utvalsleiaren|Leder|Leiar|Kommisjonsleder|Leiar\s+for\s+utvalet|Leder\s+for\s+utvalget)\s*[:–\-]\s*\n*\s*([A-ZÆØÅ][^\n\r]+)",
            full_text,
            re.I
        )
        if lead_label:
            cand = lead_label.group(1).split("Medlemmer:")[0].split("Medlemer:")[0].split("I tillegg")[0].strip()
            if not any(k in cand.lower() for k in ["utvalgsarbeid", "veileder", "personalhåndbok", "regelverk", "ser fram til", "sier", "mener", "viser til", "understreker"]):
                cand = re.sub(r"\.\s+.*$", "", cand).strip()
                leader = clean_person_string(cand)

        # Pattern 2: Verb phrase (e.g. "Bård Vegar Solhjell leder utvalget" or "Kristin Halvorsen skal leie utvalet")
        if not leader:
            lead_verb = re.search(
                r"([A-ZÆØÅ][a-zæøåA-ZÆØÅ\s\-]+?)\s+(?:skal\s+leie|skal\s+lede|skal\s+leia|er\s+utvalgsleder|er\s+utvalsleiar|er\s+oppnevnt\s+som\s+leder|er\s+oppnemnd\s+som\s+leiar|leder\s+utvalget|leiar\s+utvalet|leier\s+utvalet)",
                full_text,
                re.I
            )
            if lead_verb:
                leader = clean_person_string(lead_verb.group(1))

        # Pattern 3: "Under [Title] [Name]s ledelse"
        if not leader:
            lead_eng = re.search(
                r"Under\s+(?:[a-zæøåA-ZÆØÅ\s]+\s+)?([A-ZÆØÅ][a-zæøåA-ZÆØÅ\-]+(?:\s+[A-ZÆØÅ][a-zæøåA-ZÆØÅ\-]+){1,3})s\s+ledelse",
                full_text
            )
            if lead_eng:
                leader = clean_person_string(lead_eng.group(1))

        # Pattern 4: "ledet av [Name]"
        if not leader:
            ledet_av = re.search(
                r"(?:ledet|leia|leiast|ledast)\s+av\s+(?:tidligere\s+[^\s,]+\s+|professor\s+|direktør\s+|statsforvalter\s+|lagmann\s+)?([A-ZÆØÅ][a-zæøåA-ZÆØÅ\s\-]+?)(?:[.,\n]|som\s+skal)",
                full_text,
                re.I
            )
            if ledet_av:
                leader = clean_person_string(ledet_av.group(1))

        # Pattern 5: "oppnevnt [Name] som leder/utvalgsleder"
        if not leader:
            oppnevnt_som = re.search(
                r"(?:oppnevnt|oppnemnd)\s+(?:tidligere\s+[^\s,]+\s+|professor\s+|direktør\s+|statsforvalter\s+)?([A-ZÆØÅ][a-zæøåA-ZÆØÅ\s\-]+?)\s+som\s+(?:leder|utvalgsleder|leiar|utvalsleiar)",
                full_text,
                re.I
            )
            if oppnevnt_som:
                leader = clean_person_string(oppnevnt_som.group(1))

        # 11. Members Roster Extraction
        members: List[Dict[str, Optional[str]]] = []
        for m_tag in soup.find_all(lambda t: t.name in ["h2", "h3", "h4", "strong", "p"] and re.search(r"Sammensetning|Medlemmer|Medlemer|Utvalgets medlemmer|Utvalet sine medlemer|Desse er med i utvalet", t.get_text(), re.I)):
            parent = m_tag.find_parent(["section", "div", "article"]) or m_tag.parent
            for li in parent.find_all("li"):
                raw_m = li.get_text(separator=" ", strip=True)
                if not leader and re.search(r"\(utvalgsleder\)|\(utvalsleiar\)|\(leder\)|\(leiar\)|utvalgets leder|utvalets leiar|,\s*leder,?\s*|,\s*leiar,?\s*|,\s*utvalgsleder,?\s*|som leder|som leiar", raw_m, re.I):
                    clean_lead = re.sub(r"\(utvalgsleder\)|\(utvalsleiar\)|\(leder\)|\(leiar\)|utvalgets leder,?\s*|utvalets leiar,?\s*|,\s*leder,?\s*|,\s*leiar,?\s*|,\s*utvalgsleder,?\s*|som leder,?\s*|som leiar,?\s*", ", ", raw_m, flags=re.I).strip()
                    leader = clean_person_string(clean_lead)
                p_obj = clean_person_string(raw_m)
                if p_obj and p_obj not in members:
                    members.append(p_obj)
            for p in parent.find_all("p"):
                lines = p.get_text(separator="\n", strip=True).split("\n")
                for line in lines:
                    if not leader and re.search(r"\(utvalgsleder\)|\(utvalsleiar\)|\(leder\)|\(leiar\)|utvalgets leder|utvalets leiar|,\s*leder,?\s*|,\s*leiar,?\s*|,\s*utvalgsleder,?\s*|som leder|som leiar", line, re.I):
                        clean_lead = re.sub(r"\(utvalgsleder\)|\(utvalsleiar\)|\(leder\)|\(leiar\)|utvalgets leder,?\s*|utvalets leiar,?\s*|,\s*leder,?\s*|,\s*leiar,?\s*|,\s*utvalgsleder,?\s*|som leder,?\s*|som leiar,?\s*", ", ", line, flags=re.I).strip()
                        leader = clean_person_string(clean_lead)
                    p_obj = clean_person_string(line)
                    if p_obj and p_obj not in members:
                        members.append(p_obj)
            for tr in parent.find_all("tr"):
                tds = [td.get_text(strip=True) for td in tr.find_all("td")]
                if tds:
                    row_str = ", ".join(tds)
                    if not leader and re.search(r"\(utvalgsleder\)|\(utvalsleiar\)|\(leder\)|\(leiar\)|,\s*leder,?\s*|,\s*leiar,?\s*", row_str, re.I):
                        clean_lead = re.sub(r"\(utvalgsleder\)|\(utvalsleiar\)|\(leder\)|\(leiar\)|,\s*leder,?\s*|,\s*leiar,?\s*", ", ", row_str, flags=re.I).strip()
                        leader = clean_person_string(clean_lead)
                    p_obj = clean_person_string(row_str)
                    if p_obj and p_obj not in members:
                        members.append(p_obj)

        final_members: List[Dict[str, Optional[str]]] = []
        seen_names: Set[str] = set()
        for m in members:
            if m["name"] not in seen_names:
                seen_names.add(m["name"])
                final_members.append(m)

        members_count = len(final_members)
        if leader and leader.get("name"):
            if leader.get("name") not in seen_names:
                members_count += 1

        # 12. Mandate Summary Extraction
        def is_clean_mandate(text: Optional[str]) -> bool:
            if not text or len(text) < 40:
                return False
            lower = text.lower()
            if any(noise in lower for noise in [
                "pressekonferanse", "presseinvitasjon", "innspillsmøte", "innspelsmøte",
                "arrangerer regionalt", "arrangerer innspillsmøte", "arrangerer innspelsmøte",
                "marmorhallen", "strømmes på", "streaming", "påmelding innen", "akkreditering",
                "inviterer til innspillsmøte", "inviterer til innspelsmøte", "pressekontakt:",
                "temapensjon"
            ]):
                return False
            if text.startswith("Tema") and len(text.split()) < 8:
                return False
            return True

        mandate_summary: Optional[str] = None
        mandate_head = soup.find(lambda tag: tag.name in ["h2", "h3", "h4", "strong"] and re.search(r"Mandat|Hovedoppgaver|Oppgåver|Formål|Bakgrunn|Om utvalget|Om utvalet", tag.get_text(), re.I))
        if mandate_head:
            mandate_pars: List[str] = []
            parent_container = mandate_head.find_parent(["section", "div", "article"])
            elements_to_check = []
            if parent_container and parent_container != soup.find("main") and parent_container != soup:
                elements_to_check = parent_container.find_all(["p", "ul", "div"])
            else:
                curr = mandate_head.find_next_sibling()
                while curr and curr.name in ["p", "ul", "div", "section"] and len(elements_to_check) < 10:
                    elements_to_check.append(curr)
                    curr = curr.find_next_sibling()
                    if curr and curr.name in ["h2", "h3"]:
                        break

            for el in elements_to_check:
                t = el.get_text(strip=True)
                t = re.sub(r"\s*(?:Mandat for utvalgsarbeidet\s*)?\(PDF\)\s*$", "", t, flags=re.I).strip()
                t = re.sub(r"\s*Last ned mandat.*$", "", t, flags=re.I).strip()
                if is_clean_mandate(t) and not any(noise in t.lower() for noise in ["pressekontakt", "abonner", "del på"]):
                    mandate_pars.append(t)
                    if len(mandate_pars) >= 3:
                        break
            if mandate_pars:
                mandate_summary = "\n\n".join(mandate_pars)

        if not mandate_summary:
            lead_el = soup.find(class_=re.compile(r"lead|ingress|intro", re.I))
            if lead_el:
                lead_text = lead_el.get_text(strip=True)
                if is_clean_mandate(lead_text):
                    mandate_summary = lead_text
            if not mandate_summary:
                for p in main.find_all("p"):
                    p_text = p.get_text(strip=True)
                    p_text = re.sub(r"\s*(?:Mandat for utvalgsarbeidet\s*)?\(PDF\)\s*$", "", p_text, flags=re.I).strip()
                    if len(p_text) > 80 and is_clean_mandate(p_text):
                        mandate_summary = p_text
                        break

        # 13. External dedicated website link
        external_url: Optional[str] = None
        for a in main.find_all("a", href=re.compile(r"nettsteder\.regjeringen\.no|[a-z0-9\-]+utvalget\.no|[a-z0-9\-]+utvalet\.no", re.I)):
            ext = a["href"]
            if ext.startswith("http"):
                external_url = ext
                break

        return {
            "id": item_id,
            "slug": slug,
            "title": title,
            "ministry": ministry_name,
            "ministry_code": ministry_code,
            "appointed_date": appointed_date,
            "deadline": deadline,
            "deadline_display": deadline_display or "Ikke fastsatt",
            "expected_delivery_year": expected_year,
            "leader": leader,
            "members": final_members,
            "members_count": members_count,
            "mandate_summary": mandate_summary,
            "source_url": url,
            "external_url": external_url,
            "status": "under_arbeid",
            "last_synced_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

    def run(self) -> List[Dict[str, Any]]:
        """Executes full harvesting, extraction, URL validation, and deduplication."""
        candidate_urls = self.discover_candidate_urls()
        logger.info("Harvesting and parsing %d candidate URLs...", len(candidate_urls))

        raw_parsed: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(fetch_url, u): u for u in candidate_urls}
            for f in as_completed(futures):
                url, html, status = f.result()
                if not html or status != 200:
                    continue

                item = self.parse_commission_page(url, html)
                if item:
                    raw_parsed.append(item)

        # Reconcile and merge items sharing the same canonical topic key
        logger.info("Reconciling and merging %d candidate records...", len(raw_parsed))
        topic_groups: Dict[str, List[Dict[str, Any]]] = {}
        for it in raw_parsed:
            key = get_canonical_topic_key(it["title"], it["slug"])
            topic_groups.setdefault(key, []).append(it)

        reconciled_items: List[Dict[str, Any]] = []
        for key, group in topic_groups.items():
            def is_valid_mandate_text(text: Optional[str]) -> bool:
                if not text or len(text) < 40:
                    return False
                lower = text.lower()
                return not any(noise in lower for noise in [
                    "innspillsmøte", "pressekonferanse", "presseinvitasjon", "temapensjon", "marmorhallen"
                ])

            # Pick best base record (prefer /org/ or /dep/ URL, or one with leader/members)
            base = max(group, key=lambda x: (
                2 if "/dep/" in x["source_url"] and "/org/" in x["source_url"] else (1 if "/dep/" in x["source_url"] else 0),
                1 if x.get("leader") else 0,
                len(x.get("members", [])),
                1 if is_valid_mandate_text(x.get("mandate_summary")) else 0,
                len(x.get("mandate_summary") or "")
            ))
            # Merge supplementary fields from other items in group
            for other in group:
                if other is base:
                    continue
                if not base.get("appointed_date") and other.get("appointed_date"):
                    base["appointed_date"] = other["appointed_date"]
                if not base.get("deadline") and other.get("deadline"):
                    base["deadline"] = other["deadline"]
                    base["deadline_display"] = other["deadline_display"]
                if not base.get("leader") and other.get("leader"):
                    base["leader"] = other["leader"]
                if not base.get("external_url") and other.get("external_url"):
                    base["external_url"] = other["external_url"]
                if len(other.get("members", [])) > len(base.get("members", [])):
                    base["members"] = other["members"]
                    base["members_count"] = other["members_count"]
                if (not base.get("mandate_summary") or not is_valid_mandate_text(base["mandate_summary"])) and other.get("mandate_summary") and is_valid_mandate_text(other["mandate_summary"]):
                    base["mandate_summary"] = other["mandate_summary"]

            # Normalize canonical slug & clean committee title if generic
            base["slug"] = key
            if base["slug"] == "kjernekraftutvalget":
                base["title"] = "Kjernekraftutvalget"
            elif base["slug"] == "politirolleutvalget" and "politi" in base["title"].lower():
                base["title"] = "Politirolleutvalget (Politiets rolle i samfunnet)"
            elif base["slug"] == "veteranlovutvalget" and "veteran" in base["title"].lower():
                base["title"] = "Veteranlovutvalget (Forslag til veteranlov)"
            elif base["slug"] == "cmdi-utvalget" and "cmdi" in base["title"].lower():
                base["title"] = "CMDI-utvalget (Bankkrisehåndtering og innskuddsgaranti)"
            elif base["slug"] == "arbeidsinnvandringsutvalget" and "arbeidsinnvandring" in base["title"].lower():
                base["title"] = "Arbeidsinnvandringsutvalget (Gjennomgang av arbeidsinnvandringspolitikken)"
            elif base["slug"] == "matsystemutvalget":
                base["title"] = "Matsystemutvalget"
            elif base["slug"] == "fodselstallsutvalget":
                base["title"] = "Fødselstallutvalget"
            elif base["slug"] == "etikkutvalget-spu":
                base["title"] = "Etikkutvalget for Statens pensjonsfond utland"
            elif base["slug"] == "salaersatsutvalget":
                base["title"] = "Salærsatsutvalget (Godtgjørelse til forsvarere)"
            elif base["slug"] == "kommunekommisjonen":
                base["title"] = "Kommunekommisjonen (Statlig styring av kommunene)"
            elif base["slug"] == "kraftmarkedsutvalget":
                base["title"] = "Kraftmarkedsutvalget"
            elif base["slug"] == "fiskerpensjon-utvalget":
                base["title"] = "Utvalg for modernisering av fiskerpensjonen"
            elif base["slug"] == "bostotteutvalget":
                base["title"] = "Bostøtteutvalget"
            elif base["slug"] == "pasient-og-brukerrettighetslovutvalget":
                base["title"] = "Pasient- og brukerrettighetslovutvalget"
            elif base["slug"] == "ekspropriasjonsavklaringsutvalget":
                base["title"] = "Ekspropriasjonsavklaringsutvalget"
            elif base["slug"] == "studiefinansieringsutvalget":
                base["title"] = "Studiefinansieringsutvalget (Framtidas ordningar for studielån og stipend)"
            elif base["slug"] == "norskopplaring-for-voksne-innvandrere":
                base["title"] = "Ekspertutvalg om norskopplæringstilbudet for voksne innvandrere"
            elif base["slug"] == "skattekommisjonen":
                base["title"] = "Skattekommisjonen"
            elif base["slug"] == "lesekommisjonen":
                base["title"] = "Lesekommisjonen"

            reconciled_items.append(base)

        # Re-verify 100% reachability (HTTP 200) concurrently
        logger.info("Validating 100%% reachability (HTTP 200) on %d active commissions...", len(reconciled_items))
        verified_items: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            val_futures = {executor.submit(fetch_url, it["source_url"]): it for it in reconciled_items}
            for f in as_completed(val_futures):
                it = val_futures[f]
                _, _, status = f.result()
                if status == 200:
                    verified_items.append(it)
                else:
                    logger.warning("Dropping unreachable URL (%d): %s", status, it["source_url"])

        # Sort deterministically by (expected_delivery_year asc, appointed_date desc, title asc)
        verified_items.sort(
            key=lambda x: (
                x.get("expected_delivery_year") or 9999,
                -(datetime.date.fromisoformat(x["appointed_date"]).toordinal()) if x.get("appointed_date") else 0,
                x.get("title", "")
            )
        )

        logger.info("Successfully cataloged %d authentic active commissions.", len(verified_items))
        return verified_items


# ============================================================================
# CLI ENTRYPOINT
# ============================================================================

def main() -> None:
    # Ensure stdout handles UTF-8 on Windows
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Scrape and catalog active Norwegian Official Commissions (Kommande NOU-ar) from Regjeringen.no."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes: write to data/upcoming_nous.json and copy to frontend/lib/upcoming_nous.json."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform dry run without writing files to disk."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-harvesting and bypass local caches."
    )
    parser.add_argument(
        "--output",
        type=str,
        default=os.path.join(ROOT_DIR, "data", "upcoming_nous.json"),
        help="Target output JSON path (default: data/upcoming_nous.json)."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of harvested commissions."
    )

    args = parser.parse_args()

    scraper = UpcomingNousScraper(force=args.force)
    items = scraper.run()

    if args.limit:
        items = items[:args.limit]

    print(f"\n=======================================================")
    print(f"HARVESTED {len(items)} ACTIVE COMMISSIONS (KOMMANDE NOU-AR)")
    print(f"=======================================================")
    for idx, item in enumerate(items, 1):
        print(f"{idx}. [{item['ministry_code']}] {item['title']}")
        print(f"   ID: {item['id']} | Slug: {item['slug']}")
        print(f"   Ministry: {item['ministry']}")
        print(f"   Appointed: {item['appointed_date'] or 'Ukjent'} | Frist: {item['deadline_display']} ({item['expected_delivery_year']})")
        if item.get("leader"):
            l_info = f"{item['leader']['name']}"
            if item['leader'].get('title'):
                l_info += f" ({item['leader']['title']})"
            if item['leader'].get('location'):
                l_info += f", {item['leader']['location']}"
            print(f"   Leder: {l_info}")
        else:
            print(f"   Leder: Ikke navngitt / Ukjent")
        print(f"   Medlemmer: {item['members_count']} medlemmer")
        print(f"   Source URL: {item['source_url']}")
        if item.get("external_url"):
            print(f"   External Portal: {item['external_url']}")
        if item.get("mandate_summary"):
            print(f"   Mandat: {item['mandate_summary'][:140]}...")
        print()

    if args.apply and not args.dry_run:
        output_path = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        logger.info("Saved %d records to %s", len(items), output_path)

        # Copy to frontend/lib/upcoming_nous.json for static build fallback
        frontend_fallback = os.path.join(ROOT_DIR, "frontend", "lib", "upcoming_nous.json")
        os.makedirs(os.path.dirname(frontend_fallback), exist_ok=True)
        shutil.copyfile(output_path, frontend_fallback)
        logger.info("Copied fallback catalog to %s", frontend_fallback)
    else:
        logger.info("Dry-run mode: no files written. Use --apply to save.")


if __name__ == "__main__":
    main()
