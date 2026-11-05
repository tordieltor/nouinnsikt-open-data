#!/usr/bin/env python3
"""
pipeline/repair_author_affiliations.py
----------------------------------------
Milestone 2 Remediation Engine: Author Rosters, Roles, OCR Noise Unmerging,
and Institutional Affiliations Backfill across all 1,741 NOUs in Supabase PostgreSQL.

Phases:
- Phase 1: Pre-migration snapshot export to data/backups/nou_roster_snapshot_{timestamp}.json
- Phase 2: Role & Title Scrubbing (strip "Utvalgsmedlem", "Sekretariat", "Utvalgsleder", "formann", and standalone titles)
- Phase 3: OCR Noise & Multi-Column Name Unmerging (<= 4 words per name invariant, purge TOC noise)
- Phase 4: Appointment Chunk 0-20 Scanner & Institutional Affiliation Extraction
- Phase 5: Norwegian Institutional Taxonomy Normalization & Lineage Mapping
- Phase 6: Authenticated Atomic Batch Persistence to Supabase (public.nous.document_profile + public.nou_authors)
- Phase 7: Quality Verification & Corpus-Wide Statistics Refresh (public.system_statistics)
"""

import sys
import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set, Tuple

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add workspace root and backend to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from backend.app.lib.db import (
    get_db,
    save_document_profile,
    compute_and_store_statistics,
    clean_person_name,
    is_valid_person_name,
    clear_in_memory_caches,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("repair_author_affiliations")

# ============================================================================
# 1. KNOWN ROLES, TITLES & GENERIC NOISE CONSTANTS
# ============================================================================

ROLES_TO_PURGE_FROM_ORG = {
    "utvalgsmedlem", "utvalsmedlem", "medlem", "medlemmer", "medlemer",
    "sekretariat", "sekretariatet", "sekretær", "sekretæren", "sekretærer",
    "sekretariatsleder", "sekretariatsleiar", "utvalgssekretær", "utvalssekretær",
    "utvalgsleder", "utvalsleiar", "leder", "leiar", "formann", "nestleder", "nestleiar",
    "fung. medlem", "fungerende medlem", "fung. leder", "observatør", "personlig rådgiver",
    "sakkyndig", "referent", "konsulent for utvalget", "utvalgets medlemmer", "utvalgets leder",
    "fung.", "fung", "fungerende"
}

STANDALONE_JOB_TITLES = {
    "direktør", "professor", "rådgiver", "rådgjevar", "rådgivar", "byråsjef", "advokat",
    "førstekonsulent", "avdelingsdirektør", "underdirektør", "rektor", "prorektor", "viserektor",
    "konsulent", "seniorkonsulent", "spesialkonsulent",
    "sorenskriver", "høyesterettsdommer", "lagdommer", "lagmann", "tingrettsdommer", "byrettsdommer",
    "byfogd", "førstebyfogd", "dommer", "dommerfullmektig",
    "skattejurist", "seniorskattejurist", "prosjektleder", "prosjektleiar", "seksjonssjef",
    "seksjonsleder", "seksjonsleiar", "ekspedisjonssjef", "dekan", "forsker", "seniorforsker",
    "forskningssjef", "forskningsleder", "utredningsleder", "utgreiingsleiar", "fagdirektør", "spesialrådgiver", "spesialrådgjevar",
    "seniorrådgiver", "seniorrådgjevar", "fagrådgiver", "fagrådgjevar", "divisjonsdirektør",
    "avdelingssjef", "avdelingsleiar", "kontorsjef", "fagleder", "fagleiar", "områdedirektør",
    "ordfører", "ordførar", "varaordfører", "varaordførar",
    "statssekretær", "byråd", "byrådsleder", "byrådsleiar", "byrådssekretær", "byrådsdommer",
    "formann byrådsdommer", "forbundsformann", "stortingspresident", "stortingsrepresentant",
    "banksjef", "bankrådgiver", "bankrådgjevar", "bedriftsrådgiver", "bedriftsrådgjevar", "finansrådgiver", "finansrådgjevar",
    "organisasjonssekretær", "hovedsekretær", "seniorrådgiver hovedsekretær", "velferdssekretær",
    "administrerende direktør", "administrasjonsdirektør", "konserndirektør",
    "assisterende direktør", "stipendiat", "overlege", "sjefslege", "assisterende overlege",
    "førsteamanuensis", "førstelektor", "universitetslektor", "høgskolelektor", "høgskulelektor", "postdoktor",
    "fylkesmann", "statsforvalter", "generalsekretær",
    "kommunedirektør", "rådmann", "rådmannen", "assisterende rådmann", "fylkesrådmann", "assisterende fylkesrådmann",
    "sjeføkonom", "sjefaktuar", "sjefingeniør", "overingeniør", "ingeniør",
    "siviløkonom", "sivilingeniør", "sivilagronom", "diplomingeniør", "diplomøkonom",
    "cand. jur.", "cand.jur.", "cand.jur", "cand jur",
    "cand. oecon.", "cand.oecon.", "cand.oecon", "cand oecon",
    "cand. polit.", "cand.polit.", "cand.polit", "cand polit",
    "cand. real.", "cand.real.", "cand.real", "cand real",
    "cand. mag.", "cand.mag.", "cand.mag", "cand mag",
    "cand. philol.", "cand.philol.", "cand.philol", "cand philol",
    "cand. theol.", "cand.theol.", "cand.theol", "cand theol",
    "cand. psychol.", "cand.psychol.", "cand.psychol", "cand psychol",
    "cand. med.", "cand.med.", "cand.med", "cand med",
    "cand. agric.", "cand.agric.", "cand.agric", "cand agric",
    "cand. pharm.", "cand.pharm.", "cand.pharm", "cand pharm",
    "cand. scient.", "cand.scient.", "cand.scient", "cand scient",
    "cand. merc.", "cand.merc.", "cand.merc", "cand merc",
    "dr. philos.", "dr. philos", "dr.philos.", "dr.philos", "dr philos",
    "dr. juris", "dr. juris", "dr.juris.", "dr.juris", "dr juris",
    "dr. polit.", "dr. polit", "dr.polit.", "dr.polit", "dr polit",
    "dr. scient.", "dr. scient", "dr.scient.", "dr.scient", "dr scient",
    "dr. med.", "dr. med", "dr.med.", "dr.med", "dr med",
    "dr. oecon.", "dr. oecon", "dr.oecon.", "dr.oecon", "dr oecon",
    "dr. ing.", "dr. ing", "dr.ing.", "dr.ing", "dr ing",
    "dr. art.", "dr. art", "dr.art.", "dr.art", "dr art",
    "dr. theol.", "dr. theol", "dr.theol.", "dr.theol", "dr theol",
    "ph.d.", "ph.d", "phd", "ph. d.",
    "jur.", "jur", "cand.", "cand", "dr.", "dr", "mag.", "mag", "prof.", "prof", "ing.", "ing",
    "advokat m.n.a.", "advokat mna", "høyesterettsadvokat", "forbundsleder", "forbundsleiar",
    "forretningsfører", "informasjonssjef", "kommunikasjonssjef",
    "docent", "statsadvokat", "førstestatsadvokat", "riksadvokat",
    "politioverbetjent", "politimester", "politiinspektør", "politibetjent", "politifullmektig",
    "politijurist", "politioverkonstabel", "politikonstabel", "polititjenestemann", "lensmann", "lensmannsbetjent", "lensmannsfullmektig",
    "spesialist", "psykologspesialist", "lege", "lege og forfatter", "forfatter",
    "revisor", "statsautorisert revisor", "registrert revisor",
    "og forskningsleder", "og viserektor", "og prorektor", "vicestatsadvokat",
    "lovrådgiver", "lovrådgjevar", "fungerende lovrådgiver", "fungerende lovrådgjevar",
    "fylkeslege", "kommunelege", "assisterende fylkeslege", "distriktslege",
    "fylkesagronom", "fylkesskogsjef", "fylkesveterinær", "fylkesskolesjef", "fylkesarbeidssjef",
    "student", "studenttillitsvalgt", "elev", "pensjonist", "tjenestemann", "tillitsvalgt", "hovedtillitsvalgt"
}

KNOWN_TITLE_PREFIXES = sorted(list(STANDALONE_JOB_TITLES), key=len, reverse=True)

TITLE_PREFIX_PATTERN = re.compile(
    r'^\s*(?:'
    r'prof\.|professor\b|dr\.\s*(?:philos|juris|scient|polit|med|oecon|real|art|ing|theol|psychol|habil|techn)?\.?|dr\.\b|'
    r'ing\.|ingeniør\b|direktør\b|advokat\b|dommer\b|førsteamanuensis\b|førstelektor\b|universitetslektor\b|høgskolelektor\b|'
    r'høyesterettsdommer\b|lagmann\b|lagdommer\b|sorenskriver\b|tingrettsdommer\b|byrettsdommer\b|'
    r'generalsekretær\b|forretningsfører\b|rådmann\b|stortingsrepresentant\b|ordfører\b|'
    r'sekretariatsleder\b|forbundsformann\b|avdelingsdirektør\b|underdirektør\b|byråsjef\b|konsulent\b|'
    r'førstekonsulent\b|seniorrådgiver\b|spesialrådgiver\b|forsker\b|seniorforsker\b|forskningssjef\b|'
    r'divisjonsdirektør\b|avdelingssjef\b|statssekretær\b|politimester\b|politiinspektør\b|politioverbetjent\b|'
    r'politibetjent\b|politijurist\b|lensmann\b|overlege\b|sjefslege\b|fylkeslege\b|'
    r'cand\.\s*(?:jur|real|polit|med|mag|econ|oecon|philol|psychol|agric|theol|sanit|sociol|scient|merc|ped|pharm|odont|vet)?\.?|'
    r'cand\b|jur\.\s*|jur\b|mag\.\b|mag\b|ph\.d\.?\b'
    r')\s*[/,-]?\s*',
    flags=re.IGNORECASE
)

TOC_NOISE_PATTERNS = [
    r'kjernekraftens risiko',
    r'generelle problemer',
    r'innstilling om',
    r'sammendrag',
    r'kapittel \d+',
    r'vedlegg \d+',
    r'tabell \d+',
    r'figur \d+',
    r'det kongelige',
    r'kongelig resolusjon',
    r'utredning fra',
    r'avgitt til',
    r'oversikt over',
    r'avsnitt \d+',
    r'del [iIvVxX\d]+',
    r'summary in english',
    r'summary',
]

NORWEGIAN_LOCATIONS = {
    "oslo", "bergen", "trondheim", "stavanger", "tromsø", "kristiansand", "drammen", "fredrikstad",
    "skien", "ålesund", "bodø", "horten", "københavn", "linköping", "nittedal", "bærum", "asker",
    "lillestrøm", "sandvika", "sarpsborg", "tønsberg", "sandefjord", "haugesund", "molde", "hamar",
    "gjøvik", "kongsberg", "harstad", "alta", "halden", "steinkjer", "moss", "kongsvinger", "elverum",
    "oppegård", "kolbotn", "ski", "leikanger", "voss", "førde", "sogndal", "kristiansund", "stjørdal"
}

INSTITUTIONAL_KEYWORD_PATTERNS = [
    re.compile(r'(?:[a-zæøå\-]*departement(?:et)?|[a-zæøå\-]*direktorat(?:et)?|[a-zæøå\-]*kommune(?:n)?|[a-zæøå\-]*fylkeskommune(?:n)?|[a-zæøå\-]*tilsyn(?:et)?|[a-zæøå\-]*nemnd(?:a|en)?|[a-zæøå\-]*forbund(?:et)?|[a-zæøå\-]*forening(?:en)?|[a-zæøå\-]*universitet(?:et)?|[a-zæøå\-]*høgskole(?:n)?|[a-zæøå\-]*høgskule(?:n)?|[a-zæøå\-]*institutt(?:et)?|[a-zæøå\-]*stiftelse(?:n)?|[a-zæøå\-]*sykehus(?:et)?|[a-zæøå\-]*helseforetak(?:et)?|advokatfirma(?:et)?|advokatkontor(?:et)?|politidistrikt(?:et)?|statsadvokatene|statsadvokatembet[a-zæøå]*|lagmannsrett(?:en)?|tingrett(?:en)?|høyesterett|[a-zæøå\-]*banken|norges bank|selskap(?:et)?|[a-zæøå\-]*kommisjon(?:en)?|[a-zæøå\-]*etat(?:en)?|allianse(?:n)?|union(?:en)?|aksjeselskap(?:et)?|politidirektoratet|tollvesenet|tolletaten|skatteetaten|rikstrygdeverket|statsbygg|kystverket|statens vegvesen|statskonsult)\b', re.IGNORECASE)
]

PROSE_VERB_PATTERNS = [
    re.compile(r'\b(?:er|har|mener|foreslår|viser|peker|bør|skal|kan|vil|om|at|som|ble|var|blir|avga|foreslått|oppnevnt|bistått|enige|resolusjon|spørsmål|sporsmal|somen|virksomhet|gjennom|tilbake)\b', re.IGNORECASE)
]

# ============================================================================
# 2. CANONICAL NORWEGIAN INSTITUTIONAL TAXONOMY
# ============================================================================

FULL_NAME_TAXONOMY = {
    # Academia
    r'\buniversitetet i oslo\b': 'Universitetet i Oslo (UiO)',
    r'\buniversitetet i bergen\b': 'Universitetet i Bergen (UiB)',
    r'\bnorges teknisk-naturvitenskapelige universitet\b': 'NTNU',
    r'\bnorges tekniske høgskole\b': 'NTNU',
    r'\buniversitetet i tromsø\b': 'Universitetet i Tromsø (UiT)',
    r'\bnorges arktiske universitet\b': 'Universitetet i Tromsø (UiT)',
    r'\bnorges handelshøyskole\b': 'Norges Handelshøyskole (NHH)',
    r'\bnorges miljø- og biovitenskapelige universitet\b': 'Norges miljø- og biovitenskapelige universitet (NMBU)',
    r'\bnorges landbrukshøgskole\b': 'Norges miljø- og biovitenskapelige universitet (NMBU)',
    r'\buniversitetet i stavanger\b': 'Universitetet i Stavanger (UiS)',
    r'\buniversitetet i agder\b': 'Universitetet i Agder (UiA)',
    r'\bnord universitet\b': 'Nord universitet',
    r'\boslomet\b': 'OsloMet – storbyuniversitetet',
    r'\boslomet – storbyuniversitetet\b': 'OsloMet – storbyuniversitetet',
    r'\bhøgskolen i oslo og akershus\b': 'OsloMet – storbyuniversitetet',
    r'\bhandelshøyskolen bi\b': 'Handelshøyskolen BI',
    r'\bhøgskulen på vestlandet\b': 'Høgskulen på Vestlandet (HVL)',
    r'\bhøgskolen i innlandet\b': 'Høgskolen i Innlandet (HINN)',
    r'\buniversitetet i innlandet\b': 'Høgskolen i Innlandet (HINN)',
    r'\bhøgskolen i østfold\b': 'Høgskolen i Østfold (HiØ)',
    r'\buniversitetet i sørøst-norge\b': 'Universitetet i Sørøst-Norge (USN)',
    r'\bmenighetsfakultetet\b': 'MF vitenskapelig høyskole',
    r'\bpolitihøgskolen\b': 'Politihøgskolen',
    r'\bpolitihøgskulen\b': 'Politihøgskolen',

    # Research
    r'\bstatistisk sentralbyrå\b': 'Statistisk sentralbyrå (SSB)',
    r'\bforskningsstiftelsen fafo\b': 'Forskningsstiftelsen Fafo',
    r'\bfrischsenteret\b': 'Frischsenteret',
    r'\bragnar frisch senter\b': 'Frischsenteret',
    r'\bnorsk utenrikspolitisk institutt\b': 'Norsk Utenrikspolitisk Institutt (NUPI)',
    r'\bfredsforskningsinstituttet\b': 'Fredsforskningsinstituttet (PRIO)',
    r'\btransportøkonomisk institutt\b': 'Transportøkonomisk institutt (TØI)',
    r'\bfolkehelseinstituttet\b': 'Folkehelseinstituttet (FHI)',
    r'\bstatens institutt for folkehelse\b': 'Folkehelseinstituttet (FHI)',
    r'\bnordisk institutt for studier av innovasjon, forskning og utdanning\b': 'NIFU',
    r'\bnorsk institutt for by- og regionforskning\b': 'Norsk institutt for by- og regionforskning (NIBR)',
    r'\bnorsk institutt for forskning om oppvekst, velferd og aldring\b': 'Norsk institutt for forskning om oppvekst, velferd og aldring (NOVA)',
    r'\bnorsk institutt for vannforskning\b': 'Norsk institutt for vannforskning (NIVA)',
    r'\bnorsk institutt for naturforskning\b': 'Norsk institutt for naturforskning (NINA)',
    r'\bhavforskningsinstituttet\b': 'Havforskningsinstituttet',
    r'\bmeteorologisk institutt\b': 'Meteorologisk institutt',
    r'\bnorsk regnesentral\b': 'Norsk Regnesentral',
    r'\bchr\. michelsens institutt\b': 'Chr. Michelsens Institutt (CMI)',
    r'\binstitutt for samfunnsforskning\b': 'Institutt for samfunnsforskning (ISF)',
    r'\bnorges forskningsråd\b': 'Norges forskningsråd',
    r'\boslo universitetssykehus\b': 'Oslo universitetssykehus (OUS)',
    r'\bhaukeland universitetssykehus\b': 'Haukeland universitetssykehus',
    r'\bst\. olavs hospital\b': 'St. Olavs hospital',
    r'\buniversitetssykehuset nord-norge\b': 'Universitetssykehuset Nord-Norge (UNN)',

    # Labor & Social Partners
    r'\blandsorganisasjonen i norge\b': 'Landsorganisasjonen i Norge (LO)',
    r'\bfellesforbundet\b': 'Fellesforbundet (LO)',
    r'\bfagforbundet\b': 'Fagforbundet (LO)',
    r'\bnorsk tjenestemannslag\b': 'Norsk Tjenestemannslag (NTL / LO)',
    r'\bhandel og kontor i norge\b': 'Handel og Kontor i Norge (LO)',
    r'\byrkesorganisasjonenes sentralforbund\b': 'Yrkesorganisasjonenes Sentralforbund (YS)',
    r'\butdanningsforbundet\b': 'Utdanningsforbundet (Unio)',
    r'\bnorsk sykepleierforbund\b': 'Norsk Sykepleierforbund (Unio)',
    r'\bpolitiets fellesforbund\b': 'Politiets Fellesforbund (Unio)',
    r'\bforskerforbundet\b': 'Forskerforbundet (Unio)',
    r'\bden norske legeforening\b': 'Den norske legeforening (Akademikerne)',
    r'\bden norske advokatforening\b': 'Den Norske Advokatforening',
    r'\bnorges juristforbund\b': 'Norges Juristforbund (Akademikerne)',

    # Employer & Industry
    r'\bnho transport\b': 'NHO Transport',
    r'\bnho reiseliv\b': 'NHO Reiseliv',
    r'\bnho service og handel\b': 'NHO Service og Handel',
    r'\bnho sjøfart\b': 'NHO Sjøfart',
    r'\bnho luftfart\b': 'NHO Luftfart',
    r'\bnho logistikk og transport\b': 'NHO Logistikk og Transport',
    r'\bnho mat og drikke\b': 'NHO Mat og Drikke',
    r'\bnho byggenæringen\b': 'NHO Byggenæringen',
    r'\bnho geneo\b': 'NHO Geneo',
    r'\bnho elektro\b': 'NHO Elektro',
    r'\bnho abelia\b': 'Abelia (NHO)',
    r'\bnæringslivets hovedorganisasjon\b': 'Næringslivets Hovedorganisasjon (NHO)',
    r'\bnorsk arbeidsgiverforening\b': 'Næringslivets Hovedorganisasjon (NHO)',
    r'\bkommunenes sentralforbund\b': 'KS',
    r'\bnorske kommuners sentralforbund\b': 'KS',
    r'\bhovedorganisasjonen virke\b': 'Hovedorganisasjonen Virke',
    r'\barbeidsgiverforeningen spekter\b': 'Arbeidsgiverforeningen Spekter',
    r'\bnorges bondelag\b': 'Norges Bondelag',
    r'\bnorsk bonde- og småbrukarlag\b': 'Norsk Bonde- og Småbrukarlag',
    r'\bnorges fiskarlag\b': 'Norges Fiskarlag',
    r'\bnorges rederiforbund\b': 'Norges Rederiforbund',
    r'\bfinans norge\b': 'Finans Norge',
    r'\bfunksjonshemmedes fellesorganisasjon\b': 'Funksjonshemmedes Fellesorganisasjon (FFO)',

    # Ministries
    r'\bfinansdepartementet\b': 'Finansdepartementet',
    r'\bfinans- og tolldepartementet\b': 'Finansdepartementet',
    r'\bjustisdepartementet\b': 'Justisdepartementet',
    r'\bjustis- og politidepartementet\b': 'Justisdepartementet',
    r'\bjustis- og beredskapsdepartementet\b': 'Justisdepartementet',
    r'\bhelsedepartementet\b': 'Helse- og omsorgsdepartementet',
    r'\bsosialdepartementet\b': 'Helse- og omsorgsdepartementet',
    r'\bhelse- og omsorgsdepartementet\b': 'Helse- og omsorgsdepartementet',
    r'\bkunnskapsdepartementet\b': 'Kunnskapsdepartementet',
    r'\bkirke- og undervisningsdepartementet\b': 'Kunnskapsdepartementet',
    r'\butdannings- og forskningsdepartementet\b': 'Kunnskapsdepartementet',
    r'\barbeidsdepartementet\b': 'Arbeids- og inkluderingsdepartementet',
    r'\bkommunal- og arbeidsdepartementet\b': 'Arbeids- og inkluderingsdepartementet',
    r'\barbeids- og inkluderingsdepartementet\b': 'Arbeids- og inkluderingsdepartementet',
    r'\bkommunaldepartementet\b': 'Kommunal- og distriktsdepartementet',
    r'\bkommunal- og distriktsdepartementet\b': 'Kommunal- og distriktsdepartementet',
    r'\bnæringsdepartementet\b': 'Nærings- og fiskeridepartementet',
    r'\bnærings- og fiskeridepartementet\b': 'Nærings- og fiskeridepartementet',
    r'\butenriksdepartementet\b': 'Utenriksdepartementet',
    r'\bforsvarsdepartementet\b': 'Forsvarsdepartementet',
    r'\bsamferdselsdepartementet\b': 'Samferdselsdepartementet',
    r'\bmiljøverndepartementet\b': 'Klima- og miljødepartementet',
    r'\bklima- og miljødepartementet\b': 'Klima- og miljødepartementet',
    r'\bolje- og energidepartementet\b': 'Energidepartementet',
    r'\benergidepartementet\b': 'Energidepartementet',
    r'\blandbruksdepartementet\b': 'Landbruks- og matdepartementet',
    r'\blandbruks- og matdepartementet\b': 'Landbruks- og matdepartementet',
    r'\bbarne- og familiedepartementet\b': 'Barne- og familiedepartementet',
    r'\bkulturdepartementet\b': 'Kultur- og likestillingsdepartementet',
    r'\bdigitaliserings- og forvaltningsdepartementet\b': 'Digitaliserings- og forvaltningsdepartementet',
    r'\bstatsministerens kontor\b': 'Statsministerens kontor',

    # Directorates & Courts
    r'\bskatteetaten\b': 'Skatteetaten',
    r'\bskattedirektoratet\b': 'Skatteetaten',
    r'\bfinanstilsynet\b': 'Finanstilsynet',
    r'\bkredittilsynet\b': 'Finanstilsynet',
    r'\bkonkurransetilsynet\b': 'Konkurransetilsynet',
    r'\bnorges bank\b': 'Norges Bank',
    r'\briksrevisjonen\b': 'Riksrevisjonen',
    r'\barbeidstilsynet\b': 'Arbeidstilsynet',
    r'\bsjøfartsdirektoratet\b': 'Sjøfartsdirektoratet',
    r'\bluftfartstilsynet\b': 'Luftfartstilsynet',
    r'\bmiljødirektoratet\b': 'Miljødirektoratet',
    r'\bhelsedirektoratet\b': 'Helsedirektoratet',
    r'\butdanningsdirektoratet\b': 'Utdanningsdirektoratet',
    r'\bstatens vegvesen\b': 'Statens vegvesen',
    r'\bkystverket\b': 'Kystverket',
    r'\bstatsbygg\b': 'Statsbygg',
    r'\btolletaten\b': 'Tolletaten',
    r'\bdatatilsynet\b': 'Datatilsynet',
    r'\bforbrukertilsynet\b': 'Forbrukertilsynet',
    r'\bforbrukerrådet\b': 'Forbrukerrådet',
    r'\bnorges høyesterett\b': 'Norges Høyesterett',
    r'\bhøyesterett\b': 'Norges Høyesterett',
    r'\bborgarting lagmannsrett\b': 'Borgarting lagmannsrett',
    r'\bgulating lagmannsrett\b': 'Gulating lagmannsrett',
    r'\bfrostating lagmannsrett\b': 'Frostating lagmannsrett',
    r'\beidsivating lagmannsrett\b': 'Eidsivating lagmannsrett',
    r'\bhålogaland lagmannsrett\b': 'Hålogaland lagmannsrett',
    r'\bagder lagmannsrett\b': 'Agder lagmannsrett',
    r'\boslo tingrett\b': 'Oslo tingrett',
    r'\bbergen tingrett\b': 'Bergen tingrett',
    r'\btrøndelag tingrett\b': 'Trøndelag tingrett',
    r'\briksadvokaten\b': 'Riksadvokaten',
    r'\bstatsadvokatene\b': 'Statsadvokatene',
    r'\bstatsadvokatembet[a-zæøå]*\b': 'Statsadvokatene',
    r'\bstatskonsult\b': 'Statskonsult',
    r'\brikstrygdeverket\b': 'Rikstrygdeverket',
    r'\bstatens lånekasse for utdanning\b': 'Statens lånekasse for utdanning',
    r'\blånekassen\b': 'Statens lånekasse for utdanning',
    r'\bdistriktenes utbyggingsfond\b': 'Distriktenes utbyggingsfond',
    r'\bstatens forurensningstilsyn\b': 'Statens forurensningstilsyn (SFT)',
    r'\bstatens personalkontor\b': 'Statens personalkontor',
    r'\bstatens pensjonskasse\b': 'Statens pensjonskasse (SPK)',
    r'\bstatens kornforretning\b': 'Statens kornforretning',
    r'\bsentralforbund\b': 'KS',
}

EXACT_CASE_ACRONYMS = {
    r'\bUiO\b': 'Universitetet i Oslo (UiO)',
    r'\bUiB\b': 'Universitetet i Bergen (UiB)',
    r'\bNTNU\b': 'NTNU',
    r'\bNTH\b': 'NTNU',
    r'\bUiT\b': 'Universitetet i Tromsø (UiT)',
    r'\bNHH\b': 'Norges Handelshøyskole (NHH)',
    r'\bNMBU\b': 'Norges miljø- og biovitenskapelige universitet (NMBU)',
    r'\bNLH\b': 'Norges miljø- og biovitenskapelige universitet (NMBU)',
    r'\bUiS\b': 'Universitetet i Stavanger (UiS)',
    r'\bUiA\b': 'Universitetet i Agder (UiA)',
    r'\bHiOA\b': 'OsloMet – storbyuniversitetet',
    r'\bBI\b': 'Handelshøyskolen BI',
    r'\bHVL\b': 'Høgskulen på Vestlandet (HVL)',
    r'\bHINN\b': 'Høgskolen i Innlandet (HINN)',
    r'\bHiØ\b': 'Høgskolen i Østfold (HiØ)',
    r'\bUSN\b': 'Universitetet i Sørøst-Norge (USN)',
    r'\bSSB\b': 'Statistisk sentralbyrå (SSB)',
    r'\bFafo\b': 'Forskningsstiftelsen Fafo',
    r'\bFAFO\b': 'Forskningsstiftelsen Fafo',
    r'\bSINTEF\b': 'SINTEF',
    r'\bNUPI\b': 'Norsk Utenrikspolitisk Institutt (NUPI)',
    r'\bPRIO\b': 'Fredsforskningsinstituttet (PRIO)',
    r'\bTØI\b': 'Transportøkonomisk institutt (TØI)',
    r'\bFHI\b': 'Folkehelseinstituttet (FHI)',
    r'\bNIFU\b': 'NIFU',
    r'\bNIBR\b': 'Norsk institutt for by- og regionforskning (NIBR)',
    r'\bNOVA\b': 'Norsk institutt for forskning om oppvekst, velferd og aldring (NOVA)',
    r'\bNIVA\b': 'Norsk institutt for vannforskning (NIVA)',
    r'\bNINA\b': 'Norsk institutt for naturforskning (NINA)',
    r'\bLO\b': 'Landsorganisasjonen i Norge (LO)',
    r'\bYS\b': 'Yrkesorganisasjonenes Sentralforbund (YS)',
    r'\bUnio\b': 'Unio',
    r'\bUNIO\b': 'Unio',
    r'\bAkademikerne\b': 'Akademikerne',
    r'\bNHO\b': 'Næringslivets Hovedorganisasjon (NHO)',
    r'\bKS\b': 'KS',
    r'\bVirke\b': 'Hovedorganisasjonen Virke',
    r'\bVIRKE\b': 'Hovedorganisasjonen Virke',
    r'\bSpekter\b': 'Arbeidsgiverforeningen Spekter',
    r'\bSPEKTER\b': 'Arbeidsgiverforeningen Spekter',
    r'\bNAV\b': 'NAV',
    r'\bDSB\b': 'Direktoratet for samfunnssikkerhet og beredskap (DSB)',
    r'\bOUS\b': 'Oslo universitetssykehus (OUS)',
    r'\bUNN\b': 'Universitetssykehuset Nord-Norge (UNN)',
    r'\bSMK\b': 'Statsministerens kontor',
    r'\bDFD\b': 'Digitaliserings- og forvaltningsdepartementet',
    r'\bUD\b': 'Utenriksdepartementet',
    r'\bFD\b': 'Forsvarsdepartementet',
    r'\bSD\b': 'Samferdselsdepartementet',
    r'\bKLD\b': 'Klima- og miljødepartementet',
    r'\bOED\b': 'Energidepartementet',
    r'\bLMD\b': 'Landbruks- og matdepartementet',
    r'\bBFD\b': 'Barne- og familiedepartementet',
    r'\bKUD\b': 'Kultur- og likestillingsdepartementet',
    r'\bFFO\b': 'Funksjonshemmedes Fellesorganisasjon (FFO)',
}

COMPILED_FULL = [(re.compile(p, re.IGNORECASE), c) for p, c in FULL_NAME_TAXONOMY.items()]
COMPILED_ACRONYMS = [(re.compile(p), c) for p, c in EXACT_CASE_ACRONYMS.items()]

def normalize_institution_name(raw_org: Optional[str]) -> Optional[str]:
    """Normalizes an organization string against the canonical taxonomy or cleans formatting."""
    if not raw_org or not isinstance(raw_org, str):
        return None
    
    clean = raw_org.replace('\xad', '').replace('\xa0', ' ')
    clean = re.sub(r'\s*\([^)]*$', '', clean)
    clean = re.sub(r'\s*\([^)]*\)', '', clean)
    clean = re.sub(r'\s+', ' ', clean).strip(' ,.:;()\t\n\r[]"\'')
    if not clean or len(clean) < 2:
        return None
    
    clean_lower = clean.lower()
    if clean_lower in NORWEGIAN_LOCATIONS or clean_lower in ROLES_TO_PURGE_FROM_ORG or clean_lower in STANDALONE_JOB_TITLES:
        return None
    
    # Check full taxonomy names
    for pattern_re, canonical in COMPILED_FULL:
        if pattern_re.search(clean_lower):
            return canonical
        
    # Check exact case acronyms
    for pattern_re, canonical in COMPILED_ACRONYMS:
        if pattern_re.search(clean):
            return canonical
        
    # Check if it's a known municipality or district
    if "kommune" in clean_lower or "fylkeskommune" in clean_lower or "politidistrikt" in clean_lower or "tingrett" in clean_lower:
        if not re.search(r'\b(?:er|har|mener|gjelder|nettopp|senere|tilsyn|med|ot|lov|loven|kommunesektoren|utdan)\b', clean_lower):
            return clean.title() if clean.islower() else clean

    return None


def is_valid_institution(org: Optional[str]) -> bool:
    """Validates whether a candidate string is an authentic institution/organization."""
    if not org or not isinstance(org, str):
        return False
    clean = org.replace('\xad', '').replace('\xa0', ' ')
    clean = re.sub(r'\s*\([^)]*$', '', clean)
    clean = re.sub(r'\s*\([^)]*\)', '', clean)
    clean = re.sub(r'\s+', ' ', clean).strip(' ,.:;()\t\n\r[]"\'')
    if len(clean) < 2:
        return False
    
    # 1. Direct taxonomy match
    norm = normalize_institution_name(clean)
    if norm:
        return True
        
    clean_low = clean.lower()
    if clean_low in STANDALONE_JOB_TITLES or clean_low in ROLES_TO_PURGE_FROM_ORG or clean_low in NORWEGIAN_LOCATIONS:
        return False
        
    # Check prose verbs / words / sentence markers
    if re.search(r'\b(?:er|har|mener|foreslår|viser|peker|bør|skal|kan|vil|om|at|som|ble|var|blir|avga|foreslått|oppnevnt|bistått|enige|resolusjon|spørsmål|sporsmal|somen|virksomhet|gjennom|tilbake|gjelder|nettopp|senere|tilsyn|ot|lov|loven|kommunesektoren|utdan|samme|tidligere)\b', clean_low) or ':' in org or ';' in org:
        return False
    if clean_low.startswith('samme ') or ' med ny ' in clean_low or ' med nye ' in clean_low:
        return False
        
    # Check if all tokens are standalone titles / degrees / prepositions
    tokens = clean_low.split()
    if all(t.strip('.,()') in STANDALONE_JOB_TITLES or t.strip('.,()') in ROLES_TO_PURGE_FROM_ORG or t.strip('.,()') in {"dr", "juris", "philos", "scient", "med", "m.n.a", "og", "i", "ved", "ph.d", "ph.d.", "cand", "mag", "av", "for"} for t in tokens):
        return False
        
    words = clean.split()
    if len(words) > 6:
        return False
        
    # Check if multiple person names ("Name1 og Name2")
    if " og " in clean:
        parts = clean.split(" og ")
        if len(parts) == 2 and all(is_valid_person_name(clean_person_name(p)) and len(p.split()) in [2, 3] for p in parts):
            return False

    # Check institutional keyword pattern
    for kp in INSTITUTIONAL_KEYWORD_PATTERNS:
        if kp.search(clean):
            # Ensure it does not end in a pure job title suffix
            if re.search(r'(?:sjef|leder|leiar|rådgiver|rådgjevar|betjent|inspektør|dommer|mann)$', clean_low) and not any(clean_low.endswith(s) for s in ["lensmann", "fylkesmann", "statsmann", "sysselmann"]):
                return False
            return True
            
    return False


# ============================================================================
# 3. ROLE & TITLE SCRUBBING
# ============================================================================

PREPOSITIONS = [" i ", " ved ", " for ", " på ", " hos ", " fra "]
DISCIPLINE_PREP_PATTERN = re.compile(
    r'^(?:[A-ZÆØÅa-zæøå\s\-]+?\s+)?(?:i|for)\s+[A-ZÆØÅa-zæøå\s\-]+?\s+(?:ved|på|fra|i|hos)\s+',
    re.IGNORECASE
)

def scrub_organization_string(org_str: Optional[str]) -> Optional[str]:
    """
    Scrubs role pollution ("Utvalgsmedlem", "Sekretariat", "Utvalgsleder", "formann"),
    standalone job titles, OCR prose noise, and extracts institution if a title+institution pattern is present.
    """
    if not org_str or not isinstance(org_str, str):
        return None
    
    cleaned = org_str.replace('\xad', '').replace('\xa0', ' ')
    cleaned = re.sub(r',([^\s])', r', \1', cleaned)
    cleaned = re.sub(r'\s*\([^)]*$', '', cleaned)
    cleaned = re.sub(r'\s*\([^)]*\)', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' ,.:;()\t\n\r[]"\'')
    if not cleaned:
        return None
    
    # If contains soft-hyphen remnants, resolution sentences, or multiple sentences > 45 chars without taxonomy match
    if len(cleaned) > 45 and not any(p.search(cleaned) for p, _ in COMPILED_FULL) and not any(p.search(cleaned) for p, _ in COMPILED_ACRONYMS):
        if re.search(r'\b(?:resolusjon|oppnevnt|utvalg|gjennom|virksomhet|tilbake|spørsmål|sporsmal|somen|ved kongelig|ved kgl|etter forslag|gjelder|nettopp)\b', cleaned, re.IGNORECASE) or '.' in cleaned[:-1]:
            return None
        
    clean_lower = cleaned.lower()
    
    # Check if purely a role string or location
    if clean_lower in ROLES_TO_PURGE_FROM_ORG or clean_lower in NORWEGIAN_LOCATIONS:
        return None
    
    # Check if purely a standalone job title
    if clean_lower in STANDALONE_JOB_TITLES:
        return None
    
    # Strip modifier prefixes ('tidligere ', 'pensjonert ', 'fhv. ', 'tidlegare ')
    for mod in ['tidligere ', 'pensjonert ', 'fhv. ', 'fhv ', 'tidlegare ']:
        if clean_lower.startswith(mod):
            sub_mod = cleaned[len(mod):].strip()
            sub_mod_clean = scrub_organization_string(sub_mod)
            return sub_mod_clean

    # Strip compound slash titles ('førstestatsadvokat/embetsleder ved ...' -> '...')
    if '/' in cleaned:
        sub_slash = re.sub(r'^[a-zæøå\s]+/[a-zæøå\s]+(?:\s+(?:ved|i|hos|på|for)\s+|,\s*)', '', cleaned, flags=re.IGNORECASE).strip()
        if sub_slash != cleaned and is_valid_institution(sub_slash):
            return normalize_institution_name(sub_slash) or sub_slash

    # Check token-based standalone titles (e.g. "Professor dr. juris", "docent ph.d", "Formann byrådsdommer")
    tokens = clean_lower.split()
    if all(t.strip('.,()') in STANDALONE_JOB_TITLES or t.strip('.,()') in ROLES_TO_PURGE_FROM_ORG or t.strip('.,()') in {"dr", "juris", "philos", "scient", "med", "m.n.a", "og", "i", "ved", "ph.d", "ph.d.", "cand", "mag", "av", "for"} for t in tokens):
        if not any(pattern_re.search(clean_lower) for pattern_re, _ in COMPILED_FULL) and not any(pat.search(cleaned) for pat, _ in COMPILED_ACRONYMS):
            return None

    # Check title ending with job title / person name (e.g. "A/S Trondheim Trafikkselskap. Utredningsleder ...")
    if ". " in cleaned:
        parts = cleaned.split(". ")
        if is_valid_institution(parts[0]):
            return normalize_institution_name(parts[0]) or parts[0]

    # Strip discipline prepositions (e.g. "Professor i rettsvitenskap ved Universitetet i Bergen" -> "Universitetet i Bergen")
    m_disc = DISCIPLINE_PREP_PATTERN.match(cleaned)
    if m_disc:
        sub_disc = cleaned[m_disc.end():].strip()
        sub_disc = re.sub(r'\s+', ' ', sub_disc)
        if is_valid_institution(sub_disc):
            return normalize_institution_name(sub_disc) or sub_disc

    # Strip known title prefixes attached to organizations
    for prefix in KNOWN_TITLE_PREFIXES:
        if clean_lower == prefix:
            return None
        
        # Check prepositions (" i ", " ved ", " for ", " på ", " hos ", " fra ")
        for prep in PREPOSITIONS:
            pat = prefix + prep
            if clean_lower.startswith(pat):
                sub = cleaned[len(pat):].strip()
                sub = re.sub(r'\s+', ' ', sub).strip(' ,.:;()[]"\'')
                if is_valid_institution(sub):
                    return normalize_institution_name(sub) or sub
                return None
                
        # Check comma separator ("Direktør, NHO")
        if clean_lower.startswith(prefix + ", "):
            sub = cleaned[len(prefix) + 2:].strip()
            sub = re.sub(r'\s+', ' ', sub).strip(' ,.:;()[]"\'')
            if is_valid_institution(sub):
                return normalize_institution_name(sub) or sub
            return None
            
        # Check space separator ("Direktør NHO")
        if clean_lower.startswith(prefix + " "):
            sub = cleaned[len(prefix) + 1:].strip()
            for prep_word in ["i ", "ved ", "for ", "på ", "hos ", "fra "]:
                if sub.lower().startswith(prep_word):
                    sub = sub[len(prep_word):].strip()
                    break
            sub = re.sub(r'\s+', ' ', sub).strip(' ,.:;()[]"\'')
            if is_valid_institution(sub):
                return normalize_institution_name(sub) or sub
            return None

    # Run taxonomy normalizer or validate
    norm = normalize_institution_name(cleaned)
    if norm:
        return norm
    
    if is_valid_institution(cleaned):
        return cleaned

    return None


# ============================================================================
# 4. OCR NOISE PURGING & MULTI-COLUMN NAME UNMERGING
# ============================================================================

NON_PERSON_START_WORDS = {
    'den', 'det', 'de', 'dette', 'denne', 'disse', 'enkelte', 'noen', 'enhver', 'flere', 'mange', 'alle',
    'slik', 'slike', 'hver', 'hvordan', 'hvorfor', 'hva', 'hvem', 'hvilke', 'hvilken', 'hvor', 'når',
    'som', 'for', 'ved', 'om', 'etter', 'på', 'av', 'til', 'fra', 'med', 'i', 'over', 'under', 'mot',
    'mellom', 'uten', 'innen', 'utenfor', 'innenfor', 'særlig', 'betydningen', 'bruken', 'innholdet',
    'innsamling', 'lagring', 'utlevering', 'bearbeiding', 'lovbestemmelser', 'taushetspliktbestemmelser',
    'ulikheter', 'oppnevningen', 'farer', 'ansvar', 'analyse', 'bakgrunn', 'dokument', 'dokumentet',
    'effekt', 'effekten', 'energi', 'forbud', 'forhold', 'forslag', 'hensyn', 'innspill', 'kostnad',
    'kostnader', 'krav', 'mandat', 'metode', 'modell', 'mål', 'nedbør', 'omfang', 'omfanget', 'oppgave',
    'oppsummering', 'ordning', 'oversikt', 'preferanser', 'prinsipp', 'problem', 'rapport', 'rapporten',
    'regulering', 'risiko', 'samarbeid', 'sikring', 'sikringstiltak', 'status', 'system', 'tiltak',
    'utfordring', 'utredning', 'utredningen', 'utvikling', 'utviklingstrekk', 'varighet', 'vedlegg',
    'virkning', 'vurdering', 'økonomi', 'deltid', 'kompensasjon', 'sysselsatte', 'tariffregulert',
    'unio', 'spekter', 'europa', 'nordisk', 'teknisk', 'nasjonalt', 'grunneiere', 'grunneiers',
    'vannledninger', 'høydedata', 'kommunenes', 'flight', 'collision', 'usage', 'motion', 'sea',
    'eurocopter', 'westland', 'cat', 'fs', 'fo', 'delutredning', 'nærmere', 'forutsetninger'
}

NON_PERSON_END_WORDS = {
    'av', 'for', 'om', 'til', 'på', 'med', 'i', 'fra', 'ved', 'mot', 'og', 'eller', 'men', 'samt',
    'et', 'en', 'ei', 'den', 'det', 'de', 'som', 'hvor', 'når', 'hva', 'deres', 'sin', 'sitt', 'sine'
}

ALL_CAPS_HEADER_RE = re.compile(r'^[A-ZÆØÅ\s\-–—]{5,}$')
NAVIGATION_NOISE_RE = re.compile(
    r'\b(?:'
    r'neste|forrige|last\s+dokumentet|følgende\s+fullstendig|suspensjon\s+dersom|'
    r'parlamentets\s+rådets|rådets\s+begge|les\s+dokumentet|last\s+ned\s+dokument|'
    r'til\s+forsida|til\s+toppen|eva\s+schei\s+neste'
    r')\b',
    re.IGNORECASE
)
OCR_MATH_CLUSTER_RE = re.compile(
    r'\b(?:Pn|Qn|Sn|Un|Vn|Wn|Yn|Snn)\b|'
    r'^\s*(?:En\s+In|En\s+Sn|In\s+Un|Vn\s+In|Wn\s+Vn|Yn\s+Snn|Yn\s+Un)\s*$',
    re.IGNORECASE
)
LEGAL_SECTION_NOISE_RE = re.compile(
    r'\b(?:'
    r's-rett|s-reglene|s-analyse|a-forskriften|rekvisisjonsloven|forsyningsloven|'
    r'lovutkastene|lov\s+teknologi|verdipapirforetak|garantistillelse|kredittderivater|'
    r'organisasjonsform|interessekonflikter|tilbakekall\s+s-rett|godkjennelse\s+s-rett|'
    r'offentlig\s+tillatelse|søknadsprosedyrer|foreløpige\s+først|generelle\s+omfang|'
    r'leilighetsvis|spørsmålet\s+regulerte|virksomhet\s+nærmere|lobo\s+media|norsk\s+vilkår'
    r')\b',
    re.IGNORECASE
)
LANDSLIDE_NOISE_RE = re.compile(
    r'\b(?:gjerdrumskredet|rissaskredet|skjeggestadskredet|skredet|byneset\s+trondheim|kvikkleireskred|verdalsskredet)\b',
    re.IGNORECASE
)
REPORT_TEXT_FRAGMENT_RE = re.compile(
    r'\b(?:'
    r'vi\s+de\s+derfor|introduksjon\s+hvilken|forpliktelse\s+konkretisering|utgangspunkt\s+hvilke|'
    r'temaer\s+demokratisk|formålet\s+negativ|negativ\s+uttrekk|petroleumsfondets|jagland\s+bondevik|'
    r'bondevik\s+nedsettelse|miljø\s+tobakk|rapporter\s+ns|frivillige\s+codes|global\s+compact|'
    r'compact\s+historie|ds\s+europa|the\s+global\s+reporting|es\s+ansvarsdeling|es\s+hensyn|'
    r'es\s+kommunenes|es\s+tilgang|es\s+tydeliggjøre|ryan\s+leder\s+annegrete|dagheid\s+fure\s+utvalgssekretær|'
    r'tilgjengelig\s+effekter|tilgjengelige\s+forskning|ns\s+særlig|norsk\s+folkerettslige|'
    r'sammenfatning\s+skjematisk|direkte\s+inntektsskatter|forbrukersubsidier|fødselspenger\s+sykepenger|'
    r'uførepensjon\s+alderspensjoner|avgiftsfritak\s+frivillig|særavgifter\s+historisk|malmtrafikk\s+ofotbanen'
    r')\b',
    re.IGNORECASE
)
PUBLISHER_LIBRARY_NOISE_RE = re.compile(
    r'\b(?:universitetsforlaget|depotbiblioteket|nasjonalbiblioteket|nb\s+rana)\b',
    re.IGNORECASE
)

def is_toc_or_chapter_noise(name: str) -> bool:
    """Checks if a string is TOC noise, a chapter title, or document text rather than a person name."""
    if not name or not isinstance(name, str):
        return True
    
    clean = name.replace('\xad', '').strip(' \t\n\r"\'')
    if not clean or len(clean) < 3:
        return True
    
    # Check all-caps headers >= 5 chars
    if ALL_CAPS_HEADER_RE.search(clean):
        return True

    # Check navigation noise
    if NAVIGATION_NOISE_RE.search(clean):
        return True

    # Check math/OCR tokens
    if OCR_MATH_CLUSTER_RE.search(clean):
        return True

    # Check legal/section noise
    if LEGAL_SECTION_NOISE_RE.search(clean):
        return True

    # Check landslide disaster noise
    if LANDSLIDE_NOISE_RE.search(clean):
        return True

    # Check report text fragments
    if REPORT_TEXT_FRAGMENT_RE.search(clean):
        return True

    # Check publisher / library noise
    if PUBLISHER_LIBRARY_NOISE_RE.search(clean):
        return True
    
    # Check trailing punctuation or dashes
    if clean.endswith(('.', '...', ':', ';', '?', '!', '-', '–')):
        return True
    
    # Check start with lowercase
    if clean[0].islower():
        return True
    
    # Check digits with 3 or more digits (e.g. 1974:22)
    if re.search(r'\d{3,}', clean):
        return True

    words = clean.split()
    if not words or len(words) < 2:
        return True

    # Check unspaced long word tokens or CamelCase inside token
    for word in words:
        if len(word) > 20:
            return True
        if re.search(r'[a-zæøå][A-ZÆØÅ]', word):
            return True
        if word.endswith(('-', '–')):
            return True

    # Non-person first word check
    first_w = words[0].lower().rstrip('.:,;')
    if first_w in NON_PERSON_START_WORDS:
        return True
        
    # Non-person last word check
    last_w = words[-1].lower().rstrip('.:,;')
    if last_w in NON_PERSON_END_WORDS:
        return True

    # Repeated words ratio check (e.g. "Dokumentet Dokumentet Dokumentet")
    if len(set(w.lower() for w in words)) < len(words) * 0.75:
        return True

    # English system keywords
    if any(w.lower() in {'avoidance', 'operational', 'severity', 'influencing', 'monitoring', 'state', 'healthand', 'sikorsky'} for w in words):
        return True

    if len(clean) > 45:
        return True

    # Check institutional/committee start words
    clean_lower = clean.lower()
    if re.match(r'^\s*(?:utvalget|utvalet|kommisjonen|styringsgruppen|hovedkommitéen|hovedkomiteen|arbeidsgruppen|departementet|sekretariatet|tilrår|tilrr|mandat|etter\s+forslag|ved\s+kgl|side\s+kap|kap\b|del\b|avsnitt\b|forslag\b|oversikt\b|innledning\b|alminnelige\b|generelt\b|forord\b|sammendrag\b|oppsummering\b|lovspeil\b)', clean_lower):
        return True

    # Check TOC / administrative noise keywords (excluding legitimate surname 'Stabell')
    name_no_stabell = re.sub(r'\bstabell\b', '', clean, flags=re.IGNORECASE)
    if re.search(
        r'(?:'
        r'kapittel|vedlegg|innhold|oversikt|innledning|alminnelige|generelt|'
        r'forord|sammendrag|oppsummering|f-tabellen|tabell|del\s+\d+|lovspeil|'
        r'persondata|persondatasystem|helikopter|arbeidsmiljø|arbeidsmiljo|tariffavtale|'
        r'tilrår|tilrr|merverdiavgift|merverdiavgif|styringsgruppen|hovedkommitéen|hovedkomiteen|'
        r'utlevering|bearbeiding|innsamling|lagring|på sporet|differansekontrakter|'
        r'pengemarkedsinstrumenter|transparencydirektivet|varederivater|avgiftsavregningen|'
        r'momskompensasjonsordningen|verdalsskredet|trappetrinnsmodell|ozonødeleggende|'
        r'antikollisjonsvarslingssystem|eierskapsutøvelse|håndhevelse|forsikringsselskaper|'
        r'feltundersøkelsen|eierbegrensning|verdipapirfondsandeler|matrikulære|kartverkets|'
        r'støtabsorbsjon|oljeindustrien|innflyging|helidekk'
        r')',
        name_no_stabell,
        re.IGNORECASE
    ):
        return True

    for pat in TOC_NOISE_PATTERNS:
        if re.search(pat, clean_lower):
            return True
        
    return False


def unmerge_multicolumn_name(name_str: str) -> List[str]:
    """
    Unmerges multi-column concatenated names or names joined with 'og' / commas,
    strictly enforcing the <= 4 words per name invariant.
    """
    if not name_str or not isinstance(name_str, str):
        return []
    
    cleaned = clean_person_name(name_str)
    while True:
        new_cleaned = TITLE_PREFIX_PATTERN.sub('', cleaned)
        if new_cleaned == cleaned:
            break
        cleaned = new_cleaned.strip()
    
    # If trailing word ends in hyphen (e.g. 'Kristin Holberg Else-'), clean trailing cut-off
    if cleaned and cleaned.split() and cleaned.split()[-1].endswith(('-', '–')):
        sub_words = cleaned.split()[:-1]
        cand = " ".join(sub_words).strip()
        if cand and is_valid_person_name(cand) and not is_toc_or_chapter_noise(cand):
            cleaned = cand

    if not cleaned or is_toc_or_chapter_noise(cleaned):
        return []
    
    # Check if joined with " og " or " / " or " and "
    if " og " in cleaned:
        parts = cleaned.split(" og ")
        result = []
        for p in parts:
            p_clean = clean_person_name(p).strip()
            while True:
                new_p = TITLE_PREFIX_PATTERN.sub('', p_clean)
                if new_p == p_clean:
                    break
                p_clean = new_p.strip()
            if is_valid_person_name(p_clean) and len(p_clean.split()) <= 4 and not is_toc_or_chapter_noise(p_clean):
                result.append(p_clean)
        if result:
            return result
        
    if " / " in cleaned:
        parts = cleaned.split(" / ")
        result = []
        for p in parts:
            p_clean = clean_person_name(p).strip()
            while True:
                new_p = TITLE_PREFIX_PATTERN.sub('', p_clean)
                if new_p == p_clean:
                    break
                p_clean = new_p.strip()
            if is_valid_person_name(p_clean) and len(p_clean.split()) <= 4 and not is_toc_or_chapter_noise(p_clean):
                result.append(p_clean)
        if result:
            return result

    words = cleaned.split()
    if len(words) <= 4:
        if is_valid_person_name(cleaned):
            return [cleaned]
        return []
    
    # If words > 4, attempt multi-column splitting
    if len(words) == 5:
        cand1 = " ".join(words[:3])
        cand2 = " ".join(words[3:])
        if is_valid_person_name(cand1) and is_valid_person_name(cand2):
            return [cand1, cand2]
        cand1 = " ".join(words[:2])
        cand2 = " ".join(words[2:])
        if is_valid_person_name(cand1) and is_valid_person_name(cand2):
            return [cand1, cand2]
        
    elif len(words) == 6:
        cand1 = " ".join(words[:3])
        cand2 = " ".join(words[3:])
        if is_valid_person_name(cand1) and is_valid_person_name(cand2):
            return [cand1, cand2]
        c1, c2, c3 = " ".join(words[:2]), " ".join(words[2:4]), " ".join(words[4:])
        if is_valid_person_name(c1) and is_valid_person_name(c2) and is_valid_person_name(c3):
            return [c1, c2, c3]
        
    elif len(words) == 7 or len(words) == 8:
        mid = len(words) // 2
        cand1 = " ".join(words[:mid])
        cand2 = " ".join(words[mid:])
        if is_valid_person_name(cand1) and is_valid_person_name(cand2):
            return [cand1, cand2]

    return []


# ============================================================================
# 5. APPOINTMENT CHUNK SCANNER & AFFILIATION EXTRACTION
# ============================================================================

def extract_affiliations_from_nou_chunks(
    chunks: List[str],
    existing_members: List[str],
    existing_leader: Optional[str] = None
) -> Dict[str, str]:
    """
    Scans NOU text chunks 0-20 to extract authentic institutional affiliations
    for known committee members and leader.
    Returns mapping: { person_name: organization_string }
    """
    extracted_affiliations: Dict[str, str] = {}
    if not chunks:
        return extracted_affiliations
    
    all_target_names = list(existing_members)
    if existing_leader:
        all_target_names.append(existing_leader)
        
    target_lookup = {clean_person_name(n).lower(): n for n in all_target_names if n}

    combined_text = "\n".join(chunks)
    lines = combined_text.splitlines()

    current_context_org = None

    for idx, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean or len(line_clean) < 3:
            continue
        
        # Skip transmittal recipient lines (e.g. "Til Justisdepartementet")
        if re.match(r'^\s*Til\s+[A-ZÆØÅa-zæøå\s\-]+departementet', line_clean, re.IGNORECASE):
            continue

        # Check context header: "etter forslag fra [Organisasjon]:" or "representanter for [Organisasjon]:"
        m_context = re.search(r'(?:etter\s+forslag\s+fra|representant(?:er)?\s+for|fra\s+organisasjonene)\s+([A-ZÆØÅ][^\n\r:–-]+?)[:–-]', line_clean, re.IGNORECASE)
        if m_context:
            cand_context_org = scrub_organization_string(m_context.group(1))
            if cand_context_org and is_valid_institution(cand_context_org):
                current_context_org = cand_context_org
                continue
        elif line_clean.startswith(('#', '==', '--', 'Del ', 'Kapittel ', 'Innhold')):
            current_context_org = None

        # Check each target in this line
        for norm_name_lower, full_name in target_lookup.items():
            if norm_name_lower in line_clean.lower():
                pos = line_clean.lower().find(norm_name_lower)
                after_text = line_clean[pos + len(norm_name_lower):].strip()
                before_text = line_clean[:pos].strip()
                
                # Check parenthetical: (Org)
                m_par = re.search(r'^\s*\(([^)]+)\)', after_text)
                if m_par:
                    c_org = scrub_organization_string(m_par.group(1))
                    if c_org and is_valid_institution(c_org):
                        extracted_affiliations[full_name] = c_org
                        continue
                        
                # Check comma: , Org
                if after_text.startswith(','):
                    sub = after_text.lstrip(', ')
                    clauses = sub.split(',')
                    for cl in clauses:
                        c_org = scrub_organization_string(cl)
                        if c_org and is_valid_institution(c_org):
                            extracted_affiliations[full_name] = c_org
                            break
                    if full_name in extracted_affiliations:
                        continue
                        
                # Check full taxonomy in after_text
                for pat_re, canonical in COMPILED_FULL:
                    if pat_re.search(after_text):
                        extracted_affiliations[full_name] = canonical
                        break
                if full_name in extracted_affiliations:
                    continue
                    
                # Check acronym in after_text
                for pat_re, canonical in COMPILED_ACRONYMS:
                    if pat_re.search(after_text):
                        extracted_affiliations[full_name] = canonical
                        break
                if full_name in extracted_affiliations:
                    continue

                # If context org active
                if current_context_org and full_name not in extracted_affiliations:
                    extracted_affiliations[full_name] = current_context_org

    # Secondary scan for continuous prose appointment paragraphs
    for full_name in all_target_names:
        if full_name in extracted_affiliations:
            continue
        for m in re.finditer(r'\b' + re.escape(full_name) + r'\b', combined_text, re.IGNORECASE):
            end_pos = m.end()
            snippet = combined_text[end_pos: end_pos + 90]
            first_delim = re.search(r'[\.\n\r;]', snippet)
            if first_delim:
                snippet = snippet[:first_delim.start()]
                
            if snippet.startswith(','):
                sub = snippet.lstrip(', ')
                for cl in sub.split(','):
                    c_org = scrub_organization_string(cl)
                    if c_org and is_valid_institution(c_org):
                        extracted_affiliations[full_name] = c_org
                        break
            elif snippet.startswith(' ('):
                m_p = re.search(r'^\s*\(([^)]+)\)', snippet)
                if m_p:
                    c_org = scrub_organization_string(m_p.group(1))
                    if c_org and is_valid_institution(c_org):
                        extracted_affiliations[full_name] = c_org
                        break
                        
            if full_name in extracted_affiliations:
                break
                
            # Full taxonomy search in snippet
            for pat_re, canonical in COMPILED_FULL:
                if pat_re.search(snippet):
                    extracted_affiliations[full_name] = canonical
                    break
            if full_name in extracted_affiliations:
                break
                
            # Acronym search in snippet
            for pat_re, canonical in COMPILED_ACRONYMS:
                if pat_re.search(snippet):
                    extracted_affiliations[full_name] = canonical
                    break
            if full_name in extracted_affiliations:
                break

    return extracted_affiliations


# ============================================================================
# 6. FULL REMEDIATION PIPELINE ENGINE
# ============================================================================

def export_pre_migration_snapshot() -> Path:
    """Exports a complete JSON backup snapshot of all NOUs and author records."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = PROJECT_ROOT / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    snapshot_file = backup_dir / f"nou_roster_snapshot_{timestamp}.json"
    
    logger.info(f"[PHASE 1] Exporting pre-migration snapshot to {snapshot_file}...")
    
    with get_db() as cur:
        cur.execute("SELECT id, title, year, document_profile FROM public.nous ORDER BY year DESC, id;")
        nous_rows = cur.fetchall()
        
        cur.execute("SELECT nou_id, name, role, organization, name_slug FROM public.nou_authors ORDER BY nou_id, role, name;")
        authors_rows = cur.fetchall()
        
    nous_dict = {}
    for r in nous_rows:
        dp = r['document_profile']
        if isinstance(dp, str):
            try:
                dp = json.loads(dp)
            except Exception:
                dp = {}
        nous_dict[str(r['id'])] = {
            "id": str(r['id']),
            "title": r['title'],
            "year": r['year'],
            "document_profile": dp
        }
        
    authors_list = []
    for a in authors_rows:
        authors_list.append({
            "nou_id": str(a['nou_id']),
            "name": a['name'],
            "role": a['role'],
            "organization": a['organization'],
            "name_slug": a['name_slug']
        })
        
    snapshot_data = {
        "timestamp": timestamp,
        "total_nous": len(nous_dict),
        "total_author_rows": len(authors_list),
        "nous": nous_dict,
        "authors": authors_list
    }
    
    with open(snapshot_file, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, ensure_ascii=False, indent=2)
        
    logger.info(f"[PHASE 1 COMPLETE] Snapshot written: {snapshot_file} ({len(nous_dict)} NOUs, {len(authors_list)} authors).")
    return snapshot_file


EXPLICIT_ROSTER_OVERHAULS = {
    "118914": {
        "leader": "Hans Petter Graver",
        "members": [
            "Jarle Bergo", "Alexander Cappelen", "Helge Eide", "Janne Haaland Matlary",
            "Gro Nystuen", "Bente Rathe", "Lasse Ruud", "Per Sandberg",
            "Anne Kristin Sydnes", "Yngvar Tveit", "Thore Johnsen"
        ],
        "secretariat": ["Tormod Cappelen Endresen", "Hilde Jervan", "Eli Lund", "Birger Vikøren"]
    },
    "156420": {
        "leader": "Rune Sæbø",
        "members": [
            "Jan Bjørland", "Per Broch Mathisen", "Atle Degré", "Ingebjørg Harto",
            "Ida Espolin Johnson", "Erik Thrane", "Hilde Vihovde", "Lisbeth Økland",
            "Kjetil Wibe", "Gaute Gravir", "Hege Dahl"
        ],
        "secretariat": []
    },
    "600370": {
        "leader": "Fredrik Sejersted",
        "members": [
            "Arnhild Dordi Gjønnes", "Morten Goller", "Hilde Hauge", "Pål Hellesylt",
            "Kari Mjølhus", "Jørgen Aardalsbakke", "Nina Ramstad Aatlo"
        ],
        "secretariat": [
            "Christina Paludan Melson", "Monica Auberg", "Marianne Guettler Monrad",
            "Peder Østbye", "Carsten Eriksrud"
        ]
    },
    "2905694": {
        "leader": "Inge Ryan",
        "members": [
            "Annegrete Bruvoll", "Ketil Matvik Foldal", "Gunnar O. Hæreid",
            "Tone Merete Muthanna", "Steinar Nordal", "Hanne Bratlie Ottesen",
            "Inger-Lise Solberg"
        ],
        "secretariat": [
            "Haakon Riekeles", "Arne Bardalen", "Hallvard Jostein Berg",
            "Tonje Røland Brasetvik", "Siri Merethe Fagerheim", "Heid Iren Haugerud",
            "Bente Ågren Høegh"
        ]
    },
    "528756": {
        "leader": "Steinar Holden",
        "members": [
            "Bente Abrahamsen", "Jan Erik Askildsen", "Anne Marie Berg",
            "Hilde Rolandsen", "Toril Solbu", "Torgeir Aarvaag Stokke",
            "Torkel Sandegren", "Anita Hegg Belgum", "Jorun Hjertø",
            "Morten Johansen", "Gerd Petter Johansen"
        ],
        "secretariat": []
    },
    "145641": {
        "leader": "Tor Ulleberg",
        "members": [
            "Ronald Geirhovd", "Gry Merete Tangen", "Ketil Karlsen",
            "Tormod Veiby", "Jorunn Seljelid", "Ingrid Årstad",
            "Sverre Austrheim", "Svein Erik Lorentzen"
        ],
        "secretariat": ["Dagheid Fure"]
    },
    "2460364": {
        "leader": "Jon Petter Rui",
        "members": [
            "Sven Arild Damslora", "Frank Hana", "Kristin Holberg",
            "Cathrine Lund", "Susanne Munch Thore", "Atle Roaldsøy",
            "Halvor Sigurdsen", "Hege Stokmo", "Amund Utne",
            "Ane Charlotte Grenstad", "Håkon Christian Grenstad"
        ],
        "secretariat": []
    },
    "477735": {
        "leader": "Gerd Ersdal",
        "members": [
            "Ole Harbitz", "Geir Riise", "Mette Cecilie Greve",
            "Henrik Toft Sørensen", "Terje Storrø", "Eva Schei"
        ],
        "secretariat": []
    },
    "digibok_2007121200055": {
        "leader": "Vidar Christiansen",
        "members": ["Trygve Holst Ringen", "Aud Kjensli", "Haakon Vennemo"],
        "secretariat": ["Øystein Aadnevik"]
    },
    "140445": {
        "leader": {"name": "Svein Efjestad", "org": "Forsvarsdepartementet"},
        "members": [
            {"name": "Espen Bergh", "org": "Justisdepartementet"},
            {"name": "Jarl Eirik Hemmer", "org": "Forsvarsdepartementet"},
            {"name": "Terje Lund", "org": "Forsvarsdepartementet"},
            {"name": "Svein E Lysgaard", "org": "Forsvarsdepartementet"},
            {"name": "Monica Lütken", "org": "Forsvarsdepartementet"},
            {"name": "Lisbeth Muhr", "org": "Energidepartementet"},
            {"name": "Vidar Refvik", "org": "Justisdepartementet"},
            {"name": "Trygve Schiøll", "org": "Statsministerens kontor"},
            {"name": "Mette Stangerhaugen", "org": "Direktoratet for samfunnssikkerhet og beredskap (DSB)"},
            "Olav Sønderland"
        ],
        "secretariat": [{"name": "Berit Strand", "org": "Forsvarsdepartementet"}]
    },
    "141003": {
        "leader": "Odd Søreide",
        "members": ["Torbjørn Iversen", "Stener Kvinnsland", "Frøydis Langmark", "Ole Nome"],
        "secretariat": []
    },
    "digibok_2013120506018": {
        "leader": "Yngvild Brandser Alvsåker",
        "members": [],
        "secretariat": []
    },
    "digibok_2008052900021": {
        "leader": None,
        "members": [],
        "secretariat": []
    },
    "digibok_2013011607055": {
        "leader": "Gunnar Garbo",
        "members": [],
        "secretariat": []
    },
    "digibok_2013102407016": {
        "leader": "Einar Høgetveit",
        "members": [],
        "secretariat": []
    }
}


def repair_single_nou_document_profile(
    nou_id: str,
    dp: dict,
    chunks: List[str]
) -> Tuple[dict, bool]:
    """
    Processes and repairs document_profile for a single NOU:
    - Scrubs role and title pollution from existing org fields
    - Purges TOC noise and unmerges multi-column names
    - Enforces leader & secretariat exclusivity (deduplication from members)
    - Scans chunks 0-20 for missing institutional affiliations
    - Returns updated (repaired_dp, has_changes)
    """
    has_changes = False
    nid_str = str(nou_id)
    if nid_str in EXPLICIT_ROSTER_OVERHAULS:
        new_dp = dict(EXPLICIT_ROSTER_OVERHAULS[nid_str])
        has_changes = True
    else:
        new_dp = dict(dp)
    
    # 1. Process Leader
    leader_raw = new_dp.get("leader") or new_dp.get("utvalgsleder") or new_dp.get("utvalsleiar")
    leader_name = ""
    leader_org = None
    
    if isinstance(leader_raw, dict):
        leader_name = leader_raw.get("name") or leader_raw.get("navn") or ""
        leader_org = leader_raw.get("org") or leader_raw.get("organization") or leader_raw.get("affiliation")
    elif isinstance(leader_raw, str):
        leader_name = leader_raw
        
    unmerged_leader = unmerge_multicolumn_name(leader_name)
    clean_leader_name = unmerged_leader[0] if unmerged_leader else clean_person_name(leader_name)
    while True:
        new_cln = TITLE_PREFIX_PATTERN.sub('', clean_leader_name)
        if new_cln == clean_leader_name:
            break
        clean_leader_name = new_cln.strip()
        
    if is_toc_or_chapter_noise(clean_leader_name):
        clean_leader_name = ""
        has_changes = True
    scrubbed_leader_org = scrub_organization_string(leader_org)
    clean_leader_name_lower = clean_leader_name.lower().strip() if clean_leader_name else ""
    
    # 2. Process Secretariat first so we have sec_names_lower for member filtering
    raw_sec = new_dp.get("secretariat") or new_dp.get("secretariat_members") or []
    if isinstance(raw_sec, str):
        raw_sec = [raw_sec]
        
    cleaned_sec: List[Dict[str, Optional[str]]] = []
    seen_sec_names: Set[str] = set()
    
    for s in raw_sec:
        s_name = ""
        s_org = None
        if isinstance(s, dict):
            s_name = s.get("name") or s.get("navn") or ""
            s_org = s.get("org") or s.get("organization") or s.get("affiliation")
        elif isinstance(s, str):
            s_name = s
            
        unmerged_names = unmerge_multicolumn_name(s_name)
        if not unmerged_names:
            continue
            
        scrubbed_s_org = scrub_organization_string(s_org)
        
        for u_name in unmerged_names:
            if is_toc_or_chapter_noise(u_name):
                has_changes = True
                continue
            u_name_clean = u_name.strip()
            u_name_lower = u_name_clean.lower()
            # Do not allow leader in secretariat
            if clean_leader_name_lower and u_name_lower == clean_leader_name_lower:
                has_changes = True
                continue
            if u_name_lower in seen_sec_names:
                has_changes = True
                continue
            seen_sec_names.add(u_name_lower)
            cleaned_sec.append({
                "name": u_name_clean,
                "org": scrubbed_s_org
            })

    # 3. Process Members (Enforce Leader and Secretariat Exclusivity)
    raw_members = new_dp.get("members") or new_dp.get("committee_members") or []
    if isinstance(raw_members, str):
        raw_members = [raw_members]
        
    cleaned_members: List[Dict[str, Optional[str]]] = []
    seen_member_names: Set[str] = set()
    
    for m in raw_members:
        m_name = ""
        m_org = None
        if isinstance(m, dict):
            m_name = m.get("name") or m.get("navn") or ""
            m_org = m.get("org") or m.get("organization") or m.get("affiliation")
        elif isinstance(m, str):
            m_name = m
            
        unmerged_names = unmerge_multicolumn_name(m_name)
        if not unmerged_names:
            continue
            
        scrubbed_m_org = scrub_organization_string(m_org)
        
        for u_name in unmerged_names:
            if is_toc_or_chapter_noise(u_name):
                has_changes = True
                continue
            u_name_clean = u_name.strip()
            u_name_lower = u_name_clean.lower()
            # Enforce leader exclusivity: leader is not a member
            if clean_leader_name_lower and u_name_lower == clean_leader_name_lower:
                has_changes = True
                continue
            # Enforce secretariat exclusivity: secretariat is not a member
            if u_name_lower in seen_sec_names:
                has_changes = True
                continue
            if u_name_lower in seen_member_names:
                has_changes = True
                continue
            seen_member_names.add(u_name_lower)
            cleaned_members.append({
                "name": u_name_clean,
                "org": scrubbed_m_org
            })

    # 4. Scan Chunks 0-20 for Missing Affiliations
    member_names = [m["name"] for m in cleaned_members]
    sec_names = [s["name"] for s in cleaned_sec]
    chunk_affiliations = extract_affiliations_from_nou_chunks(chunks, member_names, clean_leader_name)
    
    # Attach extracted affiliations to leader if missing
    if not scrubbed_leader_org and clean_leader_name in chunk_affiliations:
        scrubbed_leader_org = chunk_affiliations[clean_leader_name]
        has_changes = True
        
    # Attach extracted affiliations to members if missing
    for m in cleaned_members:
        if not m["org"] and m["name"] in chunk_affiliations:
            m["org"] = chunk_affiliations[m["name"]]
            has_changes = True

    # Attach extracted affiliations to secretariat if missing
    for s in cleaned_sec:
        if not s["org"] and s["name"] in chunk_affiliations:
            s["org"] = chunk_affiliations[s["name"]]
            has_changes = True

    if clean_leader_name:
        new_dp["leader"] = {"name": clean_leader_name, "org": scrubbed_leader_org} if scrubbed_leader_org else clean_leader_name
        new_dp["utvalgsleder"] = clean_leader_name
    else:
        new_dp.pop("leader", None)
        new_dp.pop("utvalgsleder", None)
        
    new_dp["members"] = cleaned_members
    new_dp["committee_members"] = [m["name"] for m in cleaned_members]
    new_dp["members_count"] = len(cleaned_members)
    
    new_dp["secretariat"] = cleaned_sec
    new_dp["secretariat_count"] = len(cleaned_sec)
    
    return new_dp, True


def run_full_remediation_pipeline():
    """
    Executes the 7-phase remediation pipeline across all 1,741 NOUs in Supabase PostgreSQL.
    """
    print("=" * 75)
    print("MILESTONE 2: NOU AUTHOR ROSTERS, ROLES & AFFILIATIONS BACKFILL PIPELINE")
    print("=" * 75)

    # --- Phase 1: Pre-Migration Snapshot ---
    snapshot_path = export_pre_migration_snapshot()
    
    # --- Phase 2-5: Fetch Data & Chunks, Repair & Persist ---
    logger.info("Fetching all NOUs from Supabase PostgreSQL...")
    with get_db() as cur:
        cur.execute("SELECT id, title, year, document_profile FROM public.nous ORDER BY year DESC, id;")
        nous = cur.fetchall()
        
        logger.info(f"Processing {len(nous)} NOUs with persistent cursor...")
        total_nous = len(nous)
        
        for idx, n in enumerate(nous):
            nou_id = str(n['id'])
            dp_raw = n['document_profile'] or {}
            if isinstance(dp_raw, str):
                try:
                    dp = json.loads(dp_raw)
                except Exception:
                    dp = {}
            elif isinstance(dp_raw, dict):
                dp = dp_raw
            else:
                dp = {}
                
            cur.execute("SELECT content FROM public.nou_chunks WHERE nou_id = %s AND chunk_index <= 20 ORDER BY chunk_index ASC;", (nou_id,))
            chunk_rows = cur.fetchall()
            nou_chunks = [r['content'] for r in chunk_rows if r.get('content')]
            
            repaired_dp, _ = repair_single_nou_document_profile(nou_id, dp, nou_chunks)
            
            # Save to database atomically
            save_document_profile(nou_id, repaired_dp)
            
            if (idx + 1) % 100 == 0 or (idx + 1) == total_nous:
                logger.info(f"Progress: [{idx+1}/{total_nous}] NOUs repaired and synchronized to Supabase PostgreSQL.")

    # --- Phase 6: Refresh System Statistics ---
    logger.info("[PHASE 6] Refreshing platform-wide system statistics in public.system_statistics...")
    try:
        compute_and_store_statistics()
        logger.info("[PHASE 6 COMPLETE] public.system_statistics 'fun_facts' recomputed.")
    except Exception as e:
        logger.error(f"Error computing system statistics: {e}")

    # --- Phase 7: Verification & Audit ---
    logger.info("[PHASE 7] Running quality and affiliation coverage audit...")
    with get_db() as cur:
        cur.execute("SELECT COUNT(*) as total FROM public.nou_authors;")
        total_authors = cur.fetchone()['total']
        
        cur.execute("SELECT COUNT(*) as with_org FROM public.nou_authors WHERE organization IS NOT NULL AND organization != '';")
        total_with_org = cur.fetchone()['with_org']
        
        cur.execute("SELECT COUNT(*) as role_polluted FROM public.nou_authors WHERE LOWER(organization) IN ('utvalgsmedlem', 'sekretariat', 'utvalgsleder', 'formann', 'medlem');")
        role_polluted = cur.fetchone()['role_polluted']

    coverage_pct = (total_with_org / total_authors * 100) if total_authors > 0 else 0
    print("\n" + "=" * 75)
    print("REMEDIATION AUDIT RESULTS:")
    print("=" * 75)
    print(f"Total Author Records in public.nou_authors : {total_authors}")
    print(f"Authors with Authentic Organization        : {total_with_org} ({coverage_pct:.2f}%)")
    print(f"Role Polluted Entries ('Utvalgsmedlem',etc): {role_polluted}")
    print(f"Pre-migration Snapshot File                : {snapshot_path}")
    print("=" * 75)

    if role_polluted > 0:
        logger.error(f"FAIL: Found {role_polluted} role-polluted records in public.nou_authors!")
        return False
        
    return True


if __name__ == "__main__":
    success = run_full_remediation_pipeline()
    sys.exit(0 if success else 1)
