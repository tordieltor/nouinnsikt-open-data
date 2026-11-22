# Tabellar og analysekatalogar (1972–2026)

Denne mappa inneheld alle strukturerte relasjonstabellar og ferdigprosesserte analysekatalogar for dei **1 746** offisielle NOU-utgreiingane (1972–2026), klare til direkte bruk i Excel, R, Python, Pandas og DuckDB:

- **[`relasjonstabellar/`](relasjonstabellar/)** — Alle 13 offentlege relasjonstabellar frå PostgreSQL i både **CSV** og **JSONL(.gz)** (`nous_flat.csv`, `nous.jsonl.gz`, `nou_authors.csv` med `20 205` utvalsroller, 8 tabellar for politisk etterliv og lovsporing, samt `corpus_statistics.json`).
- **[`analysekatalogar/`](analysekatalogar/)** — 21 analytiske JSON-katalogar (siteringsgrafar, dissenskatalog, mangfaldsdata, departementslinjer, LIX-lesbarheit, reformkatalog, taksonomi m.m.).
- **[`EXPORT_MANIFEST.json`](EXPORT_MANIFEST.json)** — Eksakte radtal, filstorleikar og `SHA-256`-sjekksummar for alle 50 datafiler i arkivet.
- **Dokumentasjon**: Sjå [`../DATA_DICTIONARY.md`](../DATA_DICTIONARY.md) og [`../SCHEMA.sql`](../SCHEMA.sql) for komplette feltskildringar og tabellskjema.
