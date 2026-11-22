# SQLite FTS5-database & Vektor-embeddings (1972–2026)

- **Frittståande SQLite FTS5-database (`803,19 MB` `.xz` / `2,61 GB` utpakka)**: [`nouinnsikt_fts5.sqlite.xz`](https://github.com/tordieltor/nouinnsikt-open-data/releases/tag/v1.0.0-data) under **GitHub Releases** — komplett lokal database med `nous`, `nou_authors`, alle `614 643` tekstbolkar (`nou_chunks`) og ferdigbygd `FTS5` fulltekstsøkeindeks (krev ingen server).
- **Tekstbolkar & 768-dim vektor-embeddings**: [`nou_chunks_text.jsonl.gz`](https://github.com/tordieltor/nouinnsikt-open-data/releases/tag/v1.0.0-data) (`520,67 MB`) og [`nou_chunks_embeddings_768d_float16.npz`](https://github.com/tordieltor/nouinnsikt-open-data/releases/tag/v1.0.0-data) (`845,55 MB`, `614 643 × 768` `float16`-vektorar frå `text-embedding-004`).
- **Relasjonstabellar i Git (CSV & JSONL)**: [`../01-tabellar-og-katalogar/relasjonstabellar/`](../01-tabellar-og-katalogar/relasjonstabellar/).
- **Analytiske JSON-katalogar i Git**: [`../01-tabellar-og-katalogar/analysekatalogar/`](../01-tabellar-og-katalogar/analysekatalogar/).
- **SQL-skjema & Dataordbok**: [`../SCHEMA.sql`](../SCHEMA.sql) og [`../DATA_DICTIONARY.md`](../DATA_DICTIONARY.md).
