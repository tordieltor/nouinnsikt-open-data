# NOUinnsikt — Ope Rådata-arkiv / Open Raw-Data Archive (1972–2026)

[![License: CC BY 4.0](https://img.shields.io/badge/Data%20License-CC%20BY%204.0%20%2F%20NLOD%202.0-1A365D.svg)](LICENSE)
[![Code License: MIT](https://img.shields.io/badge/Code%20License-MIT-4A7C59.svg)](LICENSE)
[![Corpus: 1,741 NOUs](https://img.shields.io/badge/NOU%20Corpus-1%2C741%20Reports%20(1972--2026)-2F5039.svg)](datasets/EXPORT_MANIFEST.json)

> **Norsk (Nynorsk):** Nettjenesta **NOUinnsikt** (`nouinnsikt.no`) er avvikla som aktiv skybasert plattform og gjort om til dette opne, permanente rådata-arkivet. Her ligg heile det strukturerte kunnskapsgrunnlaget — 54 år med *Noregs offentlege utgreiingar* (1972–2026), utvalsmedlemmar, siteringsgrafar, særmerknader/dissensar, språkmålingar (LIX), lov- og stortingssporingar, fulltekst, vektor-embeddings og KI-genererte lydsamandrag — fritt tilgjengeleg i rå, opne format utan innlogging eller kostnad.
>
> **English:** The **NOUinnsikt** public administration intelligence platform has concluded active web hosting and released its complete 54-year empirical dataset of *Official Norwegian Reports* (*Norges offentlige utredninger*, NOU 1972–2026) as an open, self-contained raw-data archive for researchers, journalists, students, civil servants, and AI/NLP developers.

---

## Empirisk omfang / Verified Corpus Metrics

| Måleparameter / Metric | Verifisert tal / Verified Count | Kjelde i arkivet / Archive File |
| :--- | :---: | :--- |
| **Offisielle NOU-utgreiingar (1972–2026)** | **1 746** (`41` nynorsk / `1 705` bokmål) | [`datasets/relational/nous_flat.csv`](datasets/relational/nous_flat.csv) & [`nous.jsonl.gz`](datasets/relational/nous.jsonl.gz) |
| **Fulltekst-ord & tekstbolkar** | **183 724 190+ ord** (`614 643` bolkar / `9 878 210+` setningar) | GitHub Release: `nou_chunks_text.jsonl.gz` & `nou_fulltext_markdown_1972_2026.tar.xz` |
| **Utvalsleiarar, medlemmar & sekretariat** | **20 205** verifiserte roller (`11 806+` unike personar) | [`datasets/relational/nou_authors.csv`](datasets/relational/nou_authors.csv) |
| **Politisk etterliv & lovsporing** | **9 603** rader fordelt på **8** relasjonstabellar (*høyringar, prop., voteringar, vedtak, lover*) | [`datasets/relational/nou_policy_lifecycle.csv`](datasets/relational/nou_policy_lifecycle.csv) m.fl. |
| **Kryssiteringar mellom NOU-ar** | **7 878** retta siteringslenkjer | [`datasets/catalogs/relations_citations.json`](datasets/catalogs/relations_citations.json) |
| **Registrerte særmerknader / dissensar** | **626** dissensar på tvers av **126** NOU-ar | [`datasets/catalogs/dissent_catalog.json`](datasets/catalogs/dissent_catalog.json) |
| **Departementslinjer (1972–2026)** | **1 091+** NOU-ar koplet mot **42** historiske $\rightarrow$ **17** moderne departement | [`datasets/catalogs/ministry_lineage.json`](datasets/catalogs/ministry_lineage.json) & [`ministry_nou_map.json`](datasets/catalogs/ministry_nou_map.json) |
| **Lesbarheit (LIX-indeks)** | **52,03 LIX** i snitt (`19,13 %` nynorskandel) | [`datasets/catalogs/language_data.json`](datasets/catalogs/language_data.json) |
| **Vektor-embeddings (`text-embedding-004`)** | **654 934 × 768-dim** vektorar (`100 %` dekning) | GitHub Release: `nou_chunks_embeddings_768d_float16.npz` |
| **Syntetiserte to-verts lydsamandrag** | **758** MP3-episodar | GitHub Release: `nou_podcasts_mp3_1972_2026.tar` |

---

## Mappestruktur / Repository Structure

Alle filer under `datasets/` (`48,89 MB` totalt på tvers av 49 datafiler i `EXPORT_MANIFEST.json`) ligg direkte i Git-repoet og kan klonast på få sekund:

```text
.
├── datasets/
│   ├── EXPORT_MANIFEST.json         # Eksakte radtal, filstorleikar og SHA-256-sjekksummar
│   ├── relational/                  # 13 relasjonstabellar frå PostgreSQL i både CSV og JSONL(.gz)
│   │   ├── nous_flat.csv            # Flat tabell over alle 1 746 NOU-ar (Excel / R / DuckDB / Pandas)
│   │   ├── nous.jsonl.gz            # Komplette NOU-objekt (samandrag, nøkkelfunn, tiltak, utvalsprofil)
│   │   ├── nou_authors.csv/.jsonl   # 20 321 utvalsroller med normalisert organisasjonstilknyting
│   │   ├── nou_policy_lifecycle.*   # 277 politiske livsløp (12 steg frå overlevering til lovvedtak)
│   │   ├── nou_hearings.*           # 348 høyringsrundar inkl. høyringsinstansar og svar
│   │   ├── nou_government_propositions.* # 968 Meld. St. og Prop. L/S/LS
│   │   ├── nou_parliamentary_cases.*     # 516 stortingssaker og komitéinnstillingar
│   │   ├── nou_parliamentary_votes.*     # 4 138 voteringar i Stortinget med partifordeling
│   │   ├── nou_parliamentary_resolutions.* # 2 230 formelle stortingsvedtak
│   │   ├── nou_enacted_legislation.*     # 345 vedtekne lover (Lovdata-kopling)
│   │   ├── nou_policy_measures.*         # 781 enkelttiltak spora mot proposisjon og lov
│   │   ├── policy_evolution_cache.*      # 58 fleirtiårige tematiske politikkutviklingsanalysar
│   │   ├── query_expansions.*            # 434 forvaltningsfaglege synonym og omgrepsutvidingar
│   │   ├── dagens_nou.*                  # 81 kuraterte høgdepunkt og faktaopplysningar
│   │   └── corpus_statistics.json        # Makrostatistikk for heile NOU-korpuset
│   └── catalogs/                    # 21 ferdigprosesserte analytiske JSON-datasett
│       ├── nou_catalog.json & reform_catalog.json
│       ├── dissent_catalog.json & diversity_catalog.json
│       ├── relations_citations.json, relations_co_occurrence.json & relations_thematic.json
│       ├── ministry_lineage.json & ministry_nou_map.json
│       ├── taxonomy.json, nou_taxonomy_map.json & nou_metadata_extra.json
│       ├── language_data.json & nynorsk_nous_catalog.json
│       ├── upcoming_nous.json & dagens_nou_100_schedule.json
│       ├── nokkeltematikker_dataset.json & flagship_policy_evolution.json
│       └── nou_index_map.json, nou_slug_map.json & extracted_artworks.json
├── podcasts/                        # Episodekatalog (podcast_catalog.csv, 758 episodar) & lenkje til MP3-arkiv
├── database/                        # Oversikt og lenkjer til SQLite FTS5-database, vektor-embeddings & SQL-skjema
├── markdown/                        # Oversikt og lenkje til alle 1 746 fulltekst Markdown-utgreiingar
├── covers/                          # Oversikt og lenkje til forsidebilete og illustrasjonsutsnitt
├── docs/                            # Statisk arkiv- og oppslagsside for nouinnsikt.no (GitHub Pages)
├── DATA_DICTIONARY.md               # Komplett kolonne- og feltspesifikasjon
├── SCHEMA.sql                       # Rein PostgreSQL + pgvector DDL-skjemadefinisjon
├── CITATION.cff                     # Akademisk siteringsfil (BibTeX / APA)
└── LICENSE                          # NLOD 2.0 + CC BY 4.0 + MIT
```

---

## Store rådata-pakkar (GitHub Releases)

Tunge rådata-arkiv (`>100 MB`) ligg under [**Releases**](../../releases) i dette repoet (gratis og uavgrensa nedlasting utan Git LFS):

1. **`nouinnsikt_fts5.sqlite.xz`** (`~310 MB`) — Komplett, frittståande SQLite-database med alle tabellar + `653 941` tekstbolkar og ferdigbygd `FTS5` fulltekstsøkeindeks.
2. **`nou_fulltext_markdown_1972_2026.tar.xz`** (`~240 MB`) — Alle **1 741 NOU-ar** som individuelle, vaska Markdown-filer (`.md`) med YAML-metadata.
3. **`nou_chunks_text.jsonl.gz`** (`~250 MB`) — Alle **653 941** tekstbolkar i strøymbar JSONL.
4. **`nou_chunks_embeddings_768d_float16.npz`** (`~960 MB`) — Komprimert NumPy-matrise (`653 941 × 768`, `text-embedding-004`).
5. **`nou_podcasts_mp3_1972_2026.tar`** (`~1,10 GB`) — **758** to-verts lydsamandrag i MP3-format (`podcasts/podcast_<id>.mp3`).
6. **`nou_covers_1972_2026.tar.xz`** (`~850 MB`) — Forsidebilete og utsnittsillustrasjonar.

---

## Kom raskt i gang / Quickstart

### Python (utan eksterne pakkar — kun standardbibliotek)

```python
import csv
import gzip
import json

# 1. Les flat NOU-oversikt (1 741 rader)
with open("datasets/relational/nous_flat.csv", encoding="utf-8") as f:
    nous = list(csv.DictReader(f))
print(f"Lastet {len(nous)} NOU-ar. Nyaste: {nous[0]['title']}")

# 2. Strøym komplette NOU-objekt med samandrag, nøkkelfunn og utvalsprofil
with gzip.open("datasets/relational/nous.jsonl.gz", "rt", encoding="utf-8") as gz:
    first_nou = json.loads(next(gz))
print(first_nou["id"], first_nou["infographic"])
```

### DuckDB (direkte SQL mot rå CSV- og JSONL-filer)

```sql
-- Topp 10 mest aktive utvalsleiarar gjennom tidene (1972–2026)
SELECT name, COUNT(*) AS leiarverv
FROM read_csv_auto('datasets/relational/nou_authors.csv')
WHERE role = 'leader'
GROUP BY name
ORDER BY leiarverv DESC
LIMIT 10;
```

---

## Kontakt / Contact

Spørsmål eller førespurnader om rådata-arkivet kan rettast til **post@nouinnsikt.no**.

---

## Lisens og kjeldetilvising / Licensing & Citation

- **Offentlege primærdokument og stortingsdata**: **NLOD 2.0** / offentleg eigedom jf. *åndsverkloven § 14* (kjelde: Regjeringen.no, Nasjonalbiblioteket, Stortinget, Lovdata).
- **NOUinnsikt-kuraterte datasett, taksonomi, dissenskatalog, relasjonsgrafar, samandrag og lydfiler**: **CC BY 4.0** (oppgje *«NOUinnsikt Open Archive (1972–2026)»*).
- **Skript, skjema og statisk landingsside**: **MIT License**.

```bibtex
@dataset{nouinnsikt_archive_2026,
  author       = {{NOUinnsikt Project}},
  title        = {{NOUinnsikt Open Raw-Data Archive: Complete Corpus, Committee Rosters, Citations, Dissents, and Legislative Lifecycle of Official Norwegian Reports (NOU 1972--2026)}},
  year         = {2026},
  version      = {1.0.0},
  publisher    = {GitHub},
  url          = {https://github.com/tordieltor/nouinnsikt-open-data}
}
```
