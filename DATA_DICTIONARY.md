# Data Dictionary — NOUinnsikt Open Raw-Data Archive (1972–2026)

This document defines the exact schemas, column types, join keys, and formats across all raw datasets in `01-tabellar-og-katalogar/relasjonstabellar/`, `01-tabellar-og-katalogar/analysekatalogar/`, `04-lydpodkastar/`, and the accompanying GitHub Release bulk archives (`v1.0.0-data`).

All text files are encoded in **UTF-8** (`\n` LF line endings for JSONL/JSON; standard RFC 4180 CSV headers for `.csv`). Every dataset file's exact row count, byte length, and `SHA-256` digest is recorded in [`01-tabellar-og-katalogar/EXPORT_MANIFEST.json`](01-tabellar-og-katalogar/EXPORT_MANIFEST.json).

---

## 1. Relational Datasets (`01-tabellar-og-katalogar/relasjonstabellar/`)

All relational tables link back to the master NOU catalog via `nou_id` $\rightarrow$ `nous.id` (e.g. `"3145481"` for modern Regjeringen.no IDs or `"digibok_2007062804027"` for historical Nasjonalbiblioteket IDs). Parliamentary votes and resolutions link via `parliamentary_case_id` $\rightarrow$ `nou_parliamentary_cases.id`.

### 1.1 Master NOU Catalog (`nous.jsonl.gz` & `nous_flat.csv` — 1,746 records)

- **`nous.jsonl.gz`** (`4.18 MB` gzipped JSON Lines): Complete lossless record per NOU including nested JSON structures:
  - `id` (`string`, PK): Canonical identifier (`regjeringen.no` document ID or `nb.no` digibok identifier).
  - `title` (`string`): Full official NOU designation and title (e.g. `"NOU 2022: 20 Et helhetlig skattesystem"`).
  - `year` (`integer`): Official publication year (`1972`–`2026`).
  - `pdf_url` (`string`): Direct verified URL to official PDF (`regjeringen.no`) or Nasjonalbiblioteket URN viewer (`nb.no`).
  - `source_url` (`string`): Official HTML landing page URL.
  - `is_nynorsk` (`boolean`): `true` for the 41 predominantly Nynorsk NOUs, `false` for the 1,705 Bokmål NOUs.
  - `nynorsk_score` (`float`): Empirical lexical Nynorsk indicator ratio (`0.0`–`1.0`).
  - `summary` (`string`): Multi-bullet Nynorsk executive summary.
  - `summary_paragraph` / `summary_4_sentences` / `summary_3_sentences` (`string | null`): Condensed executive abstracts.
  - `infographic` (`object | null`): `{ "topic": str, "findings": [str, ...], "measures": [str, ...] }`.
  - `document_profile` (`object | null`): Structured report profile containing `leader` (committee chair), `members` (appointed *utvalgsmedlemmer*), `secretariat` (secretariat staff), `mottaker` (recipient ministry), `avgitt_dato` (submission date), `page_count` (integer), and `keywords`.
  - `compound_keywords` (`array[string]`): Extracted Norwegian public-administration compound subject terms.
  - `media_mentions` (`object | null`) & `debate_assessment` (`string | null`): Public debate context.
  - `podcast_status` (`string`): `"completed"` / `"ready"` or `"none"` / `"failed"`.
  - `podcast_url` / `cover_artwork_url` (`string | null`): Portable archive-relative asset paths (`podcasts/podcast_<id>.mp3`, `covers/artwork/<id>.png`).
- **`nous_flat.csv`** (`880.5 KB` flat CSV): Tabular projection optimized for Excel, R, Stata, Pandas, and DuckDB (`id, slug, nou_ref, title, year, is_nynorsk, nynorsk_score, mottaker_ministry, delivered_date, leader_name, member_count, secretariat_count, page_count, pdf_url, source_url, podcast_status, podcast_archive_path, cover_archive_path, compound_keywords`).

### 1.2 Committee Rosters & Affiliations (`nou_authors.csv` & `nou_authors.jsonl` — 20,205 records)
Covers 11,806+ unique individuals appointed across Royal Commissions (1972–2026):
- `nou_id` (`string`, FK $\rightarrow$ `nous.id`)
- `name` (`string`): Full normalized person name (title prefixes stripped; multi-column OCR merges un-merged).
- `role` (`string`): Exclusive role per commission — `"leader"` (*utvalsleiar*), `"member"` (*utvalsmedlem*), or `"secretariat"` (*sekretariat*).
- `organization` (`string | null`): Canonical institutional affiliation or municipality/home location at appointment time.
- `name_slug` (`string`): URL/ASCII-normalized person identifier for cross-commission aggregation.

### 1.3 Political Afterlife & Legislative Lifecycle (8 Tables — 9,511 total records)
Tracks what happened to NOU proposals after submission across Regjeringen.no, Stortinget, and Lovdata:
1. **`nou_policy_lifecycle`** (`276` rows, `.csv` & `.jsonl`): Master status per tracked modern NOU (`nou_id`, `nou_reference`, `current_stage` across 12 stages from `overlevert` and `under_horing` to `vedtatt` and `lovfestet`, `responsible_ministry_code`, `has_hearing`, `has_white_paper`, `has_proposition`, `has_parliamentary_case`, `has_enacted_law`, `total_measures_count`, `adopted_measures_count`, `parliamentary_consensus_level`, `lifecycle_summary`).
2. **`nou_hearings`** (`348` rows, `.csv` & `.jsonl`): Official consultation rounds (*høringer*) with `hearing_url`, `published_date`, `deadline_date`, `total_responses_count`, `consultation_documents` JSON, and `consultation_responses` JSON (*høringssvar* organizations, dates, and URLs).
3. **`nou_government_propositions`** (`968` rows, `.csv` & `.jsonl`): Subsequent White Papers & Bills (`doc_type` in `Meld. St.`, `Prop. L`, `Prop. S`, `Prop. LS`, `reference_code`, `submitting_ministry_code`, `presented_date`, `source_url`, `key_proposals`, `nou_citations`).
4. **`nou_parliamentary_cases`** (`516` rows, `.csv` & `.jsonl`): Stortinget case records (`stortinget_sak_id`, `reference_code`, `standing_committee_name`, `rapporteur_name`, `rapporteur_party`, `committee_fractions` JSON, `recommendation_code`, `decision_text`, `stortinget_url`).
5. **`nou_parliamentary_votes`** (`4,138` rows, `.csv` & `.jsonl`): Roll-call plenary votes (`parliamentary_case_id`, `stortinget_votering_id`, `voting_timestamp`, `topic`, `total_for`, `total_against`, `total_absent`, `is_unanimous`, `party_tallies` JSON per political party, `vote_url`).
6. **`nou_parliamentary_resolutions`** (`2,230` rows, `.csv` & `.jsonl`): Formal *stortingsvedtak* (`parliamentary_case_id`, `resolution_number`, `session`, `resolution_date`, `resolution_text`, `resolution_type`).
7. **`nou_enacted_legislation`** (`345` rows, `.csv` & `.jsonl`): Enacted Lovdata statutes (`nou_id`, `parliamentary_case_id`, `lovdata_id`, `law_title`, `statute_code`, `enacted_date`, `effective_date`, `lovdata_url`, `affected_chapters`).
8. **`nou_policy_measures`** (`690` rows, `.csv` & `.jsonl`): Measure-level tracking (`nou_id`, `measure_number`, `proposal_title`, `proposal_text`, `measure_type`, `status`, `linked_white_paper_ref`, `linked_statute_ref`, `alignment_confidence`).

### 1.4 Auxiliary Knowledge Tables
- **`policy_evolution_cache.csv` / `.jsonl`** (`58` rows): Pre-synthesized multi-decade thematic policy evolution analyses (`query_hash`, `query`, `category`, `result_json`, `created_at`).
- **`query_expansions.csv` / `.jsonl`** (`434` rows): Curated Norwegian administrative synonym and historical term mappings (`query`, `expanded`).
- **`dagens_nou.csv` / `.jsonl`** (`81` rows): Curated spotlight entries and 1-sentence Nynorsk *"Visste du at...?"* empirical facts.
- **`corpus_statistics.json`**: Macro corpus aggregates (total pages, word counts, top recurring chairs/members, top organizations, ministry distributions).

---

## 2. Analytical JSON Catalogs (`01-tabellar-og-katalogar/analysekatalogar/` — 21 files)

| File | Description |
| :--- | :--- |
| `nou_catalog.json` | Complete frontend-ready structured NOU catalog (`1,746` entries with enriched metadata, summaries, and category badges). |
| `reform_catalog.json` | Curated catalog of major Norwegian public-sector reforms, connecting landmark NOUs to enacted legislation and societal outcomes. |
| `dagens_nou_100_schedule.json` | 100-day curated NOU spotlight schedule with historical context and empirical trivia. |
| `extracted_artworks.json` | Catalog of extracted visual cover artworks and illustrations across the NOU corpus. |
| `dissent_catalog.json` | **626** verified minority remarks (*dissensar / særmerknader*) across **126** NOUs with verbatim quotes, chunk indices, categories, and dissenting members. |
| `diversity_catalog.json` | 54-year demographic & corporatist representation dataset (decennial female ratios for members & chairs, 6-sector institutional balance, ministry matrix, top recurring appointees). |
| `relations_citations.json` | Directed inter-NOU citation graph (**7,878** cross-report citation edges parsed via `NOU YYYY: N` references). |
| `relations_co_occurrence.json` | Co-membership network linking individuals and commissions sharing members across 1972–2026. |
| `relations_thematic.json` | Domain cluster graph across public administration sectors. |
| `ministry_lineage.json` | Authoritative bidirectional mapping of **42** historical ministries (1972–present) to **17** modern ministries. |
| `ministry_nou_map.json` | **1,091+** verified recipient-ministry NOU assignments grouped by modern ministerial lineage. |
| `taxonomy.json` | 2-tier Norwegian public administration taxonomy (**10** primary domains, **40** subcategories). |
| `nou_taxonomy_map.json` & `nou_metadata_extra.json` | 100% corpus mapping of NOU IDs to primary/secondary taxonomy slugs and Norwegian subject labels. |
| `language_data.json` | Linguistic analysis across **183.7M words** & **9.88M sentences**: overall LIX readability (**52.03**), decade LIX trends, bureaucracy phrases, and vocabulary metrics. |
| `nynorsk_nous_catalog.json` | Catalog of Nynorsk NOUs with indicator scores and publication metadata. |
| `upcoming_nous.json` | Active official commissions (*Kommande NOU-ar*, 2026–2027 expected delivery) with mandates, chairs, member rosters, and live Regjeringen.no links. |
| `nokkeltematikker_dataset.json` & `flagship_policy_evolution.json` | 5 curated multi-decade policy evolution timelines (Taxation, Wages/Pensions, Health, Justice, Climate/Energy) with 38 comparative quote edges. |
| `nou_index_map.json` & `nou_slug_map.json` | Fast lookup maps resolving canonical semantic slugs (`nou-2022-20-...`) to numeric database IDs. |

---

## 3. GitHub Release Bulk Raw Assets (`v1.0.0-data`, 4.17 GB total)

Because GitHub caps individual Git-tracked files at `100 MB`, multi-hundred-megabyte fulltext, database, vector, and audio bundles are distributed via **GitHub Releases** on this repository (up to `2.0 GB` per asset, free unlimited downloads):

1. **`nouinnsikt_fts5.sqlite.xz`** (`803.19 MB` compressed / `2.61 GB` uncompressed): Self-contained SQLite 3 database containing `nous`, `nou_authors`, `nou_chunks` (**614,643** deduplicated rows), and a pre-built `nou_chunks_fts` **FTS5** full-text search virtual table. See [`02-sqlite-og-vektor-db/`](02-sqlite-og-vektor-db/).
2. **`nou_fulltext_markdown_1972_2026.tar.xz`** (`237.32 MB`): All **1,746** NOU reports reconstructed as individual, OCR-washed Markdown files (`markdown/<year>/nou-<year>-<num>_<id>.md`) with YAML metadata front-matter. See [`03-fulltekst-markdown/`](03-fulltekst-markdown/).
3. **`nou_chunks_text.jsonl.gz`** (`520.67 MB`): Raw stream of all **614,643** deduplicated semantic chunks (`id`, `nou_id`, `chunk_index`, `content`, `metadata`) covering **183,724,190+ words**.
4. **`nou_chunks_embeddings_768d_float16.npz`** (`845.55 MB`): Compressed NumPy archive containing `chunk_ids` (`shape: (614643,)`, UUID strings) and `embeddings_float16` (`shape: (614643, 768)`, Google `text-embedding-004` vectors).
5. **`nou_podcasts_mp3_1972_2026.tar`** (`1,373.41 MB`): **764** synthesized dual-host Norwegian analytical audio overviews (`podcasts/podcast_<nou_id>.mp3`). Catalog index in [`04-lydpodkastar/podcast_catalog.csv`](04-lydpodkastar/podcast_catalog.csv).
6. **`nou_covers_1972_2026.tar.xz`** (`386.85 MB`): **2,225** official front-page covers and cropped visual artworks. See [`05-forsidebilete/`](05-forsidebilete/).
