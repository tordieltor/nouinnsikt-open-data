# NOUinnsikt Open-Source Data Pipelines (`pipelines/`)

This folder contains the core Python harvesting, parsing, linguistic analysis, and relational extraction scripts used to build the **NOUinnsikt (1972–2026)** datasets. They are released under the **MIT License** so researchers, civil servants, journalists, and civic-tech developers can inspect the methodology, reproduce the catalogs, or continue indexing new *Official Norwegian Reports (NOUs)* in the future.

## Included Scripts

| Script | Purpose & Output |
| :--- | :--- |
| `ingest_nou.py` | Crawls new NOU reports from `regjeringen.no`, converts PDF documents to structured Markdown (`markitdown`), generates structured Nynorsk/Bokmål metadata profiles, and chunks fulltext for indexing. |
| `scrape_upcoming_nous.py` | Harvests active royal commissions (*Kommande NOU-ar*), mandates, expected delivery years, and appointed committee rosters from `regjeringen.no` $\rightarrow$ `datasets/catalogs/upcoming_nous.json`. |
| `harvest_nou_policy_lifecycle.py` | Links NOU reports across the 8-stage legislative afterlife: public hearings (`regjeringen.no`), government propositions (*Prop. L/S*, *Meld. St.*), Stortinget parliamentary cases, roll-call votes, resolutions (`data.stortinget.no`), and enacted statutes (`lovdata.no`) $\rightarrow$ `datasets/relational/nou_policy_*.csv`. |
| `extract_corpus_dissents.py` | Scans NOU fulltext chunks for formal minority remarks (*særmerknader / mindretalsdissensar*), classifying dissent types, dissenting members, and verbatim excerpts $\rightarrow$ `datasets/catalogs/dissent_catalog.json`. |
| `extract_diversity_metrics.py` | Computes 54-year gender representation across committee chairs and members, plus 6-sector corporatist affiliation balance (Academia, Public Administration, Labor/Employer orgs, Business, Civil Society, Politics/Law) $\rightarrow$ `datasets/catalogs/diversity_catalog.json`. |
| `extract_recipient_ministries.py` | Extracts and normalizes recipient ministries across 1972–2026, mapping 42 historical ministries to 17 modern ministerial lineages $\rightarrow$ `datasets/catalogs/ministry_nou_map.json` & `ministry_lineage.json`. |
| `analyze_nou_language.py` | Computes LIX readability scores, sentence/word distributions, Nynorsk/Bokmål share, and bureaucratic terminology frequencies across 183.7M words $\rightarrow$ `datasets/catalogs/language_data.json`. |
| `map_nou_taxonomy.py` | Assigns every NOU report to the 2-tier public administration taxonomy (10 primary domains, 40 subcategories) $\rightarrow$ `datasets/catalogs/nou_taxonomy_map.json`. |
| `extract_nou_compound_keywords.py` | Extracts domain-specific Norwegian compound administrative and legal terms per NOU. |
| `scrape_nou_rosters_html.py`, `repair_nou_rosters.py`, `repair_author_affiliations.py` | Parses, deduplicates, and normalizes the 20,250 committee chair, member, and secretariat records (`datasets/relational/nou_authors.csv`). |

## Environment Variables Required When Running Against Your Own Database

None of these scripts contain hardcoded credentials. To run them against your own PostgreSQL (`SCHEMA.sql`) or LLM setup, set standard environment variables in a local `.env` file:

```ini
DATABASE_URL=postgresql://localhost:5432/nouinnsikt
GEMINI_API_KEY=your_gemini_api_key_optional
```
