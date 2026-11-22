# NOUinnsikt — Ope Rådata-arkiv / Open Raw-Data Archive (1972–2026)

[![License: CC BY 4.0](https://img.shields.io/badge/Data%20License-CC%20BY%204.0%20%2F%20NLOD%202.0-1A365D.svg)](LICENSE)
[![Code License: MIT](https://img.shields.io/badge/Code%20License-MIT-4A7C59.svg)](LICENSE)
[![Corpus: 1,746 NOUs](https://img.shields.io/badge/NOU%20Corpus-1%2C746%20Reports%20(1972--2026)-2F5039.svg)](01-tabellar-og-katalogar/EXPORT_MANIFEST.json)

> **Norsk (Nynorsk):** Nettjenesta **NOUinnsikt** (`nouinnsikt.no`) er avvikla som aktiv skybasert plattform (på grunn av låg faktisk bruk frå menneske, svært mykje automatisert bot-trafikk som dreiv opp ressursbruk og faste driftskostnader, samt avgrensa tid på fritida) og gjort om til dette opne, permanente rådata-arkivet. Her ligg heile det strukturerte kunnskapsgrunnlaget — 54 år med *Noregs offentlege utgreiingar* (1972–2026), utvalsmedlemmar, siteringsgrafar, særmerknader/dissensar, språkmålingar (LIX), lov- og stortingssporingar, fulltekst, vektor-embeddings og KI-genererte lydsamandrag — fritt tilgjengeleg i rå, opne format utan innlogging eller kostnad.
>
> **English:** The **NOUinnsikt** public administration intelligence platform has concluded active web hosting (due to low human usage relative to heavy automated bot traffic/cloud infrastructure costs and limited spare-time maintenance capacity) and released its complete 54-year empirical dataset of *Official Norwegian Reports* (*Norges offentlige utredninger*, NOU 1972–2026) as an open, self-contained raw-data archive for researchers, journalists, students, civil servants, and AI/NLP developers.

---

## Empirisk omfang / Verified Corpus Metrics

| Måleparameter / Metric | Verifisert tal / Verified Count | Kjelde i arkivet / Archive File |
| :--- | :---: | :--- |
| **Offisielle NOU-utgreiingar (1972–2026)** | **1 746** (`41` nynorsk / `1 705` bokmål) | [`01-tabellar-og-katalogar/relasjonstabellar/nous_flat.csv`](01-tabellar-og-katalogar/relasjonstabellar/nous_flat.csv) & [`nous.jsonl.gz`](01-tabellar-og-katalogar/relasjonstabellar/nous.jsonl.gz) |
| **Fulltekst-ord & tekstbolkar** | **183 724 190+ ord** (`614 643` bolkar / `9 878 210+` setningar) | GitHub Release: `nou_chunks_text.jsonl.gz` & `nou_fulltext_markdown_1972_2026.tar.xz` |
| **Utvalsleiarar, medlemmar & sekretariat** | **20 205** verifiserte roller (`11 806+` unike personar) | [`01-tabellar-og-katalogar/relasjonstabellar/nou_authors.csv`](01-tabellar-og-katalogar/relasjonstabellar/nou_authors.csv) |
| **Politisk etterliv & lovsporing** | **9 511** rader fordelt på **8** relasjonstabellar (*høyringar, prop., voteringar, vedtak, lover*) | [`01-tabellar-og-katalogar/relasjonstabellar/nou_policy_lifecycle.csv`](01-tabellar-og-katalogar/relasjonstabellar/nou_policy_lifecycle.csv) m.fl. |
| **Kryssiteringar mellom NOU-ar** | **7 878** retta siteringslenkjer | [`01-tabellar-og-katalogar/analysekatalogar/relations_citations.json`](01-tabellar-og-katalogar/analysekatalogar/relations_citations.json) |
| **Registrerte særmerknader / dissensar** | **626** dissensar på tvers av **126** NOU-ar | [`01-tabellar-og-katalogar/analysekatalogar/dissent_catalog.json`](01-tabellar-og-katalogar/analysekatalogar/dissent_catalog.json) |
| **Departementslinjer (1972–2026)** | **1 091+** NOU-ar koplet mot **42** historiske $\rightarrow$ **17** moderne departement | [`01-tabellar-og-katalogar/analysekatalogar/ministry_lineage.json`](01-tabellar-og-katalogar/analysekatalogar/ministry_lineage.json) & [`ministry_nou_map.json`](01-tabellar-og-katalogar/analysekatalogar/ministry_nou_map.json) |
| **Lesbarheit (LIX-indeks)** | **52,03 LIX** i snitt (`2,35 %` hovudsakleg nynorsk) | [`01-tabellar-og-katalogar/analysekatalogar/language_data.json`](01-tabellar-og-katalogar/analysekatalogar/language_data.json) |
| **Vektor-embeddings (`text-embedding-004`)** | **614 643 × 768-dim** vektorar (`100 %` dekning) | GitHub Release: `nou_chunks_embeddings_768d_float16.npz` |
| **Syntetiserte to-verts lydsamandrag** | **764** MP3-episodar | [`04-lydpodkastar/podcast_catalog.csv`](04-lydpodkastar/podcast_catalog.csv) & GitHub Release: `nou_podcasts_mp3_1972_2026.tar` |

---

## Mappestruktur / Repository Structure

Alle datafiler under `01-tabellar-og-katalogar/` (`73,39 MB` samla på tvers av 50 verifiserte datafiler i `EXPORT_MANIFEST.json`) ligg direkte i Git-repoet og kan klonast på få sekund:

```text
.
├── 01-tabellar-og-katalogar/
│   ├── EXPORT_MANIFEST.json              # Eksakte radtal, filstorleikar og SHA-256-sjekksummar
│   ├── relasjonstabellar/                # 13 relasjonstabellar frå PostgreSQL i både CSV og JSONL(.gz)
│   │   ├── nous_flat.csv                 # Flat tabell over alle 1 746 NOU-ar (Excel / R / DuckDB / Pandas)
│   │   ├── nous.jsonl.gz                 # Komplette NOU-objekt (samandrag, nøkkelfunn, tiltak, utvalsprofil)
│   │   ├── nou_authors.csv/.jsonl        # 20 205 utvalsroller med normalisert organisasjonstilknyting
│   │   ├── nou_policy_lifecycle.*        # 276 politiske livsløp (12 steg frå overlevering til lovvedtak)
│   │   ├── nou_hearings.*                # 348 høyringsrundar inkl. høyringsinstansar og svar
│   │   ├── nou_government_propositions.* # 968 Meld. St. og Prop. L/S/LS
│   │   ├── nou_parliamentary_cases.*     # 516 stortingssaker og komitéinnstillingar
│   │   ├── nou_parliamentary_votes.*     # 4 138 voteringar i Stortinget med partifordeling
│   │   ├── nou_parliamentary_resolutions.* # 2 230 formelle stortingsvedtak
│   │   ├── nou_enacted_legislation.*     # 345 vedtekne lover (Lovdata-kopling)
│   │   ├── nou_policy_measures.*         # 690 enkelttiltak spora mot proposisjon og lov
│   │   ├── policy_evolution_cache.*      # 58 fleirtiårige tematiske politikkutviklingsanalysar
│   │   ├── query_expansions.*            # 434 forvaltningsfaglege synonym og omgrepsutvidingar
│   │   ├── dagens_nou.*                  # 81 kuraterte høgdepunkt og faktaopplysningar
│   │   └── corpus_statistics.json        # Makrostatistikk for heile NOU-korpuset
│   └── analysekatalogar/                 # 21 ferdigprosesserte analytiske JSON-datasett
│       ├── nou_catalog.json & reform_catalog.json
│       ├── dissent_catalog.json & diversity_catalog.json
│       ├── relations_citations.json, relations_co_occurrence.json & relations_thematic.json
│       ├── ministry_lineage.json & ministry_nou_map.json
│       ├── taxonomy.json, nou_taxonomy_map.json & nou_metadata_extra.json
│       ├── language_data.json & nynorsk_nous_catalog.json
│       ├── upcoming_nous.json & dagens_nou_100_schedule.json
│       ├── nokkeltematikker_dataset.json & flagship_policy_evolution.json
│       └── nou_index_map.json, nou_slug_map.json & extracted_artworks.json
├── 02-sqlite-og-vektor-db/               # Oversikt og lenkjer til SQLite FTS5-database, vektor-embeddings & SQL-skjema
├── 03-fulltekst-markdown/                # Oversikt og lenkje til alle 1 746 fulltekst Markdown-utgreiingar
├── 04-lydpodkastar/                      # Episodekatalog (podcast_catalog.csv) & lenkje til 764 MP3-podkastar
├── 05-forsidebilete/                     # Oversikt og lenkje til 2 225 forsidebilete og illustrasjonsutsnitt
├── docs/                                 # Statisk arkiv- og oppslagsside for nouinnsikt.no (GitHub Pages)
├── DATA_DICTIONARY.md                    # Komplett kolonne- og feltspesifikasjon
├── SCHEMA.sql                            # Rein PostgreSQL + pgvector DDL-skjemadefinisjon
├── CITATION.cff                          # Akademisk siteringsfil (BibTeX / APA)
└── LICENSE                               # NLOD 2.0 + CC BY 4.0 + MIT
```

---

## Store rådata-pakkar (GitHub Releases — `v1.0.0-data`, 4,17 GB totalt)

Tunge rådata-arkiv (`>100 MB`) ligg under [**Releases**](https://github.com/tordieltor/nouinnsikt-open-data/releases/tag/v1.0.0-data) i dette repoet (gratis og uavgrensa nedlasting utan Git LFS):

1. **`nouinnsikt_fts5.sqlite.xz`** (`803,19 MB` komprimert / `2,61 GB` utpakka) — Komplett, frittståande SQLite-database med alle tabellar + `614 643` tekstbolkar og ferdigbygd `FTS5` fulltekstsøkeindeks.
2. **`nou_fulltext_markdown_1972_2026.tar.xz`** (`237,32 MB`) — Alle **1 746 NOU-ar** som individuelle, vaska Markdown-filer (`.md`) med YAML-metadata.
3. **`nou_chunks_text.jsonl.gz`** (`520,67 MB`) — Alle **614 643** dedupliserte tekstbolkar i strøymbar JSONL.
4. **`nou_chunks_embeddings_768d_float16.npz`** (`845,55 MB`) — Komprimert NumPy-matrise (`614 643 × 768`, `text-embedding-004`).
5. **`nou_podcasts_mp3_1972_2026.tar`** (`1,34 GB` / `1 373,41 MB`) — **764** to-verts lydsamandrag i MP3-format (`podcasts/podcast_<id>.mp3`).
6. **`nou_covers_1972_2026.tar.xz`** (`386,85 MB`) — **2 225** forsidebilete og utsnittsillustrasjonar.

---

## Kom raskt i gang / Quickstart

### Python (utan eksterne pakkar — kun standardbibliotek)

```python
import csv
import gzip
import json

# 1. Les flat NOU-oversikt (1 746 rader)
with open("01-tabellar-og-katalogar/relasjonstabellar/nous_flat.csv", encoding="utf-8") as f:
    nous = list(csv.DictReader(f))
print(f"Lastet {len(nous)} NOU-ar. Nyaste: {nous[0]['title']}")

# 2. Strøym komplette NOU-objekt med samandrag, nøkkelfunn og utvalsprofil
with gzip.open("01-tabellar-og-katalogar/relasjonstabellar/nous.jsonl.gz", "rt", encoding="utf-8") as gz:
    first_nou = json.loads(next(gz))
print(first_nou["id"], first_nou["infographic"])
```

### DuckDB (direkte SQL mot rå CSV- og JSONL-filer)

```sql
-- Topp 10 mest aktive utvalsleiarar gjennom tidene (1972–2026)
SELECT name, COUNT(*) AS leiarverv
FROM read_csv_auto('01-tabellar-og-katalogar/relasjonstabellar/nou_authors.csv')
WHERE role = 'leader'
GROUP BY name
ORDER BY leiarverv DESC
LIMIT 10;
```

---

## Metode, KI-bearbeiding og viktig atterhald om datakvalitet / Methodology & Data Quality Disclaimer

> **Viktig å vite før du brukar datasetta (Fair Warning):**
> Dette arkivet er resultat av eit uavhengig, automatisert innsamlings-, vaske- og struktureringsarbeid over 54 år med offentlege dokument (`1972–2026`). Sjølv om korpuset har vore gjennom omfattande kvalitetskontrollar, deduplisering og feilrettingar, er dataa maskinelt framstilte og **må alltid kontrollerast mot dei offisielle primærkjeldene** før bruk i juridiske, forvaltningsmessige, akademiske eller journalistiske arbeid.

1. **Innhausting, OCR-skanning og tekstkonvertering (1972–2026)**:
   - Dei **1 746 NOU-ane** spenner frå historiske, skanna trykksaker hos Nasjonalbiblioteket (`nb.no`) og UiO (`1972–1993`), via tidlege digitale PDF-ar (`1994–2013`), til moderne HTML-, EPUB- og PDF-utgåver på `regjeringen.no` (`2014–2026`).
   - Dokumenta er automatisk konverterte til Markdown (`PyMuPDF`/`markitdown`/OCR), delte opp i **614 643** semantiske tekstbolkar (`nou_chunks`) og rensa for fotnotestøy og dublettar.
   - **Dekning og kjende OCR-avvik**: `1 682 av 1 746` NOU-ar (`96,3 %`, og `100 %` etter 2010) har fullstendig brødtekst, medan rundt `64` eldre eller fleirbinds utgreiingar har kortare tekstdekning eller samandragsbolkar. I eldre skanna utgreiingar (`1972–1999`) kan det førekome OCR-feil, feiltolka tabellar/spalter eller bortfall av figurtekst.
2. **KI-genererte samandrag, strukturfelt og lydsamandrag (LLM & TTS)**:
   - Samandrag (`summary`, `summary_paragraph`, `summary_4_sentences`), strukturerte nøkkelfelt (`infographic`: hovudfunn, tilrådingar, samfunnseffekt), taksonomiklassifiseringar, tematiske politikkutviklingsanalysar og dei **764** to-verts lydsamandraga (`.mp3` + `podcast_script`) er genererte ved hjelp av store språkmodellar (Google Gemini / lokale språkmodellar) og syntetisk tale (Google Cloud TTS).
   - **KI-atterhald**: Språkmodellar kan forenkle faglege nyansar, omsetje omgrep upresist til nynorsk eller feiltolke einskilde avsnitt. KI-genererte felt og podkastar er meint som **søke- og oversiktsverktøy**, aldri som erstatning for originalteksten i utgreiinga.
3. **Automatisk uttrekk av utvalsmedlemmar, siteringar, dissensar og lovsporing**:
   - **Utvalsregisteret (`nou_authors`, 20 205 rader)**: Henta ut automatisk frå mandatsider, oversendingsbrev og fleirspalta signatursider, supplert med regelbasert organisasjonsnormalisering og fornamnsbasert kjønnsklassifisering (`~4 %` ukjent kjønn ved initialar/uvanlege namn). Historisk OCR og ujamn typografi kan gje einskilde manglande medlemmar eller ufullstendige organisasjonsnamn.
   - **Dissensar (`dissent_catalog.json`), kryssiteringar (`relations_citations.json`) og politisk etterliv (`nou_policy_lifecycle` m.fl.)**: Kartlagde maskinelt med regulære uttrykk og koplingar mot `regjeringen.no`, `data.stortinget.no` og `lovdata.no`. Automatisk kopling mellom ei NOU, ein høyringsrunde, ein proposisjon (`Prop. L` / `Meld. St.`) og eit lovvedtak kan i komplekse lovløp utelate delproposisjonar eller innehalde algoritmiske feilkoplingar.
4. **English Summary of Methodology & Limitations**:
   - This corpus was compiled through automated web/archive harvesting, PDF/OCR-to-Markdown conversion (`96.3%` full-text coverage across 1,746 reports; older scanned 1972–1999 reports contain inherent OCR and layout artifacts), regex/heuristic entity extraction (committee rosters, name-based gender inference, citation networks, minority dissents, and parliamentary lifecycle matching), and LLM/TTS synthesis (Nynorsk summaries, structured JSON profiles, and MP3 audio overviews). Always validate quotes, member rosters, and statutory references against the official primary documents at **Regjeringen.no**, **NB.no**, **Stortinget.no**, and **Lovdata.no**.

---

## Kontakt / Contact

Spørsmål eller førespurnader om rådata-arkivet kan rettast til **post@nouinnsikt.no**.

---

## Lisens og krav om kjeldetilvising / Licensing & Mandatory Attribution

- **Krav om namngjeving (CC BY 4.0)**: Alle NOUinnsikt-kuraterte datasett, taksonomi, utvalsregister, dissenskatalog, mangfaldsdata, relasjonsgrafar, lovsporingar, samandrag, vektor-embeddings og lydfiler er utarbeidde av **Tor Sivertsen Prestegard** og lisensierte under **Creative Commons Navngiving 4.0 Internasjonal (CC BY 4.0)**. All bruk, deling eller vidarebygging **krev synleg kreditering**:
  > *«Kjelde: Tor Sivertsen Prestegard — NOUinnsikt Open Raw-Data Archive (1972–2026), https://github.com/tordieltor/nouinnsikt-open-data (CC BY 4.0).»*
- **Offentlege primærdokument og stortingsdata**: **NLOD 2.0** / offentleg eigedom jf. *åndsverkloven § 14* (kjelde: Regjeringen.no, Nasjonalbiblioteket, Stortinget, Lovdata).
- **SQL-skjema og statisk landingsside**: **MIT License** (`Copyright (c) 2026 Tor Sivertsen Prestegard`).

```bibtex
@dataset{prestegard_nouinnsikt_2026,
  author       = {Prestegard, Tor Sivertsen},
  title        = {{NOUinnsikt Open Raw-Data Archive: Complete Corpus, Committee Rosters, Citations, Dissents, and Legislative Lifecycle of Official Norwegian Reports (NOU 1972--2026)}},
  year         = {2026},
  version      = {1.0.0},
  publisher    = {GitHub},
  license      = {CC-BY-4.0},
  url          = {https://github.com/tordieltor/nouinnsikt-open-data}
}
```
