-- =============================================================================
-- NOUinnsikt Open Raw-Data Archive — DuckDB SQL Quickstart Queries
-- Run with: duckdb < examples/quickstart_duckdb.sql
-- =============================================================================

-- 1. NOU publication volume and Nynorsk share by decade (1970s–2020s)
SELECT
    (CAST(year AS INTEGER) / 10) * 10 AS decade,
    COUNT(*) AS total_nous,
    SUM(CASE WHEN is_nynorsk THEN 1 ELSE 0 END) AS nynorsk_nous,
    ROUND(100.0 * SUM(CASE WHEN is_nynorsk THEN 1 ELSE 0 END) / COUNT(*), 1) AS nynorsk_pct
FROM read_csv_auto('datasets/relational/nous_flat.csv')
GROUP BY 1
ORDER BY 1;

-- 2. Top 15 recurring committee members across all roles (1972–2026)
SELECT
    name,
    COUNT(*) AS total_appointments,
    SUM(CASE WHEN role = 'leader' THEN 1 ELSE 0 END) AS as_chair,
    SUM(CASE WHEN role = 'member' THEN 1 ELSE 0 END) AS as_member,
    SUM(CASE WHEN role = 'secretariat' THEN 1 ELSE 0 END) AS as_secretariat
FROM read_csv_auto('datasets/relational/nou_authors.csv')
GROUP BY name
ORDER BY total_appointments DESC
LIMIT 15;

-- 3. Legislative lifecycle conversion summary by stage
SELECT
    current_stage,
    COUNT(*) AS nous_count,
    SUM(total_measures_count) AS proposed_measures,
    SUM(adopted_measures_count) AS adopted_measures
FROM read_csv_auto('datasets/relational/nou_policy_lifecycle.csv')
GROUP BY current_stage
ORDER BY nous_count DESC;
