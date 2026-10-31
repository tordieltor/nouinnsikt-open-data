-- =============================================================================
-- NOUinnsikt Open Raw-Data Archive — Clean Public PostgreSQL + pgvector Schema
-- =============================================================================
-- Contains ONLY the 13 public empirical research tables (1972–2026).
-- Zero private authentication, user telemetry, or administrative tables exist.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS public.nous (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    year INTEGER NOT NULL CHECK (year >= 1972 AND year <= 2035),
    pdf_url TEXT NOT NULL,
    source_url TEXT,
    summary TEXT,
    summary_paragraph TEXT,
    summary_4_sentences TEXT,
    summary_3_sentences TEXT,
    infographic JSONB,
    document_profile JSONB,
    media_mentions JSONB,
    debate_assessment TEXT,
    podcast_status TEXT DEFAULT 'none',
    podcast_url TEXT,
    cover_artwork_url TEXT,
    is_nynorsk BOOLEAN DEFAULT FALSE,
    nynorsk_score DOUBLE PRECISION,
    compound_keywords TEXT[],
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.nou_chunks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nou_id TEXT NOT NULL REFERENCES public.nous(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(768),
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.nou_authors (
    nou_id TEXT NOT NULL REFERENCES public.nous(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('leader', 'member', 'secretariat')),
    organization TEXT,
    name_slug TEXT,
    PRIMARY KEY (nou_id, name, role)
);

CREATE TABLE IF NOT EXISTS public.nou_policy_lifecycle (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nou_id TEXT NOT NULL REFERENCES public.nous(id) ON DELETE CASCADE,
    nou_reference TEXT,
    title TEXT,
    current_stage TEXT,
    stage_label_nn TEXT,
    stage_label_nb TEXT,
    delivered_date DATE,
    responsible_ministry_code TEXT,
    responsible_ministry_name TEXT,
    has_hearing BOOLEAN DEFAULT FALSE,
    has_white_paper BOOLEAN DEFAULT FALSE,
    has_proposition BOOLEAN DEFAULT FALSE,
    has_parliamentary_case BOOLEAN DEFAULT FALSE,
    has_enacted_law BOOLEAN DEFAULT FALSE,
    total_measures_count INTEGER DEFAULT 0,
    adopted_measures_count INTEGER DEFAULT 0,
    parliamentary_consensus_level TEXT,
    last_activity_date DATE,
    lifecycle_summary TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS public.nou_hearings (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nou_id TEXT NOT NULL REFERENCES public.nous(id) ON DELETE CASCADE,
    hearing_id TEXT,
    title TEXT,
    ministry_name TEXT,
    ministry_code TEXT,
    status TEXT,
    published_date DATE,
    deadline_date DATE,
    hearing_url TEXT,
    total_responses_count INTEGER DEFAULT 0,
    consultation_documents JSONB DEFAULT '[]'::jsonb,
    consultation_responses JSONB DEFAULT '[]'::jsonb,
    hearing_summary TEXT,
    departementets_vurdering TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS public.nou_government_propositions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nou_id TEXT NOT NULL REFERENCES public.nous(id) ON DELETE CASCADE,
    doc_type TEXT,
    doc_number INTEGER,
    parliamentary_session TEXT,
    reference_code TEXT,
    title TEXT,
    submitting_ministry TEXT,
    submitting_ministry_code TEXT,
    presented_date DATE,
    source_url TEXT,
    pdf_url TEXT,
    summary TEXT,
    key_proposals JSONB DEFAULT '[]'::jsonb,
    nou_citations JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS public.nou_parliamentary_cases (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nou_id TEXT NOT NULL REFERENCES public.nous(id) ON DELETE CASCADE,
    stortinget_sak_id INTEGER,
    reference_code TEXT,
    title TEXT,
    short_title TEXT,
    parliamentary_session TEXT,
    case_type TEXT,
    case_status INTEGER,
    case_status_text TEXT,
    standing_committee_id TEXT,
    standing_committee_name TEXT,
    rapporteur_person_id TEXT,
    rapporteur_name TEXT,
    rapporteur_party TEXT,
    committee_fractions JSONB DEFAULT '[]'::jsonb,
    recommendation_code TEXT,
    recommendation_date DATE,
    recommendation_title TEXT,
    decision_text TEXT,
    short_decision TEXT,
    stortinget_url TEXT,
    subjects JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS public.nou_parliamentary_votes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    parliamentary_case_id UUID REFERENCES public.nou_parliamentary_cases(id) ON DELETE CASCADE,
    stortinget_votering_id INTEGER,
    voting_timestamp TIMESTAMPTZ,
    topic TEXT,
    result_type TEXT,
    total_for INTEGER,
    total_against INTEGER,
    total_absent INTEGER,
    is_unanimous BOOLEAN,
    party_tallies JSONB DEFAULT '{}'::jsonb,
    vote_url TEXT,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS public.nou_parliamentary_resolutions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    parliamentary_case_id UUID REFERENCES public.nou_parliamentary_cases(id) ON DELETE CASCADE,
    stortingsvedtak_id TEXT,
    resolution_number INTEGER,
    session TEXT,
    resolution_date DATE,
    resolution_text TEXT,
    summary TEXT,
    resolution_type TEXT,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS public.nou_enacted_legislation (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nou_id TEXT NOT NULL REFERENCES public.nous(id) ON DELETE CASCADE,
    parliamentary_case_id UUID REFERENCES public.nou_parliamentary_cases(id) ON DELETE SET NULL,
    lovdata_id TEXT,
    law_title TEXT,
    statute_code TEXT,
    enacted_date DATE,
    effective_date DATE,
    lovdata_url TEXT,
    affected_chapters JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS public.nou_policy_measures (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nou_id TEXT NOT NULL REFERENCES public.nous(id) ON DELETE CASCADE,
    measure_number INTEGER,
    proposal_title TEXT,
    proposal_text TEXT,
    nou_chapter_reference TEXT,
    measure_type TEXT,
    status TEXT,
    linked_white_paper_ref TEXT,
    linked_statute_ref TEXT,
    alignment_confidence NUMERIC,
    alignment_explanation TEXT,
    enacted_legislation_id UUID REFERENCES public.nou_enacted_legislation(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS public.query_expansions (
    query TEXT PRIMARY KEY,
    expanded TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.dagens_nou (
    id TEXT PRIMARY KEY,
    nou_id TEXT NOT NULL REFERENCES public.nous(id) ON DELETE CASCADE,
    featured_date DATE,
    fun_fact TEXT,
    cover_image_url TEXT,
    podcast_url TEXT,
    podcast_status TEXT,
    rotation_cycle INTEGER,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nous_year ON public.nous(year);
CREATE INDEX IF NOT EXISTS idx_nou_authors_name_nou_id ON public.nou_authors(name, nou_id);
CREATE INDEX IF NOT EXISTS idx_nou_chunks_nou_chunk ON public.nou_chunks(nou_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_nou_chunks_fts ON public.nou_chunks USING gin(to_tsvector('norwegian', content));
