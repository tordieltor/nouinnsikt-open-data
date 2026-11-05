"""
Pipeline: Extract NOU Compound Keywords & Synset Thesaurus (Full Corpus Batch Ingestion)
Populates public.nous.compound_keywords text[] and document_profile['keywords'] JSONB array
across all NOU reports using algorithmic de-compounding + Gemini 2.5 Flash enrichment.
"""

import sys
import os
import re
import json
import time
import logging
import concurrent.futures
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.app.lib import db, ai

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nou_keywords_pipeline")


def extract_keywords_for_nou(row: Dict[str, Any]) -> List[str]:
    """
    Extracts high-precision compound keywords and policy synsets for a single NOU.
    Combines title compound decomposition with db.clean_and_expand_keywords filtering.
    """
    nou_id = str(row.get("id", ""))
    title = str(row.get("title", ""))
    summary = str(row.get("summary", ""))

    existing_kw = row.get("compound_keywords") or []
    if not isinstance(existing_kw, list):
        existing_kw = []

    # Algorithmic compound term decomposition on Title
    title_words = re.findall(r"\b[a-zA-Z\xe6\xf8\xe5\xc6\xd8\xc5-]{5,}\b", title)
    for w in title_words:
        stems = db.decompose_norwegian_compound_term(w)
        for st in stems:
            if len(st) >= 4:
                existing_kw.append(st.capitalize())

    # Optional Gemini 2.5 Flash Keyword Extraction for deep domain terms (if client is active)
    client = ai.get_client()
    if client:
        try:
            prompt = f"""
Du er en ekspert på norsk offentlig forvaltning og utredningsmetodikk.
Ekstraher 6-8 presise fagsubstantiv, sammensatte fagbegrep og politikkområder for denne NOU-utredningen.

Tittel: {title}
Sammendrag: {summary[:1200]}

STRIKTE REGLER FOR EMNEORD:
1. KUN sammensatte fagsubstantiv, lovverk eller konkret tema (f.eks. Kraftnett, Lokaldemokrati, Drosjeløyve, Formuesskatt, Straffeprosess, Kommuneøkonomi).
2. ALDRI generelle verb (svekker, krever, bygger, peker).
3. ALDRI ubestemte adverb eller adjektiv (lokalt, bedre, første, største).
4. ALDRI generelle eller uspesifikke ord (krav, nett, forhold, arbeid, tiltak, rapport, utvalg).
5. Svar KUN med en komma-separert liste av fagbegrep i nominativ form.
"""
            resp = ai.generate_content_with_retry(
                client=client,
                model="gemini-2.5-flash",
                contents=prompt
            )
            if resp and hasattr(resp, "text") and resp.text:
                llm_kws = [k.strip("()'\".").strip().capitalize() for k in resp.text.split(",") if len(k.strip()) >= 4]
                existing_kw.extend(llm_kws)
        except Exception as e:
            logger.warning(f"Gemini keyword extraction fallback for {nou_id}: {e}")

    # Pass all candidates through central 100% local cleaner
    final_list = db.clean_and_expand_keywords(title=title, summary=summary, existing_kws=existing_kw)
    return final_list



def update_nou_keywords(nou_id: str, keywords: List[str], current_profile: Any) -> bool:
    """Updates compound_keywords text[] and document_profile['keywords'] in Supabase PostgreSQL."""
    if not isinstance(current_profile, dict):
        try:
            current_profile = json.loads(current_profile) if current_profile else {}
        except Exception:
            current_profile = {}

    current_profile["keywords"] = keywords

    with db.get_db() as cur:
        cur.execute("""
            UPDATE public.nous 
            SET compound_keywords = %s,
                document_profile = %s::jsonb
            WHERE id = %s;
        """, (keywords, json.dumps(current_profile), nou_id))
    return True


def run_batch_keyword_extraction(limit: Optional[int] = None, force_recompute: bool = False, max_workers: int = 32):
    """Runs batch keyword extraction across the NOU corpus using high-concurrency parallel workers."""

    with db.get_db() as cur:
        if force_recompute:
            cur.execute("SELECT id, title, summary, document_profile FROM public.nous ORDER BY year DESC;")
        else:
            cur.execute("""
                SELECT id, title, summary, document_profile 
                FROM public.nous 
                WHERE compound_keywords IS NULL OR array_length(compound_keywords, 1) IS NULL OR array_length(compound_keywords, 1) = 0
                ORDER BY year DESC;
            """)
        rows = cur.fetchall()

    nous_list = [dict(r) if isinstance(r, dict) else dict(zip([col[0] for col in cur.description], r)) for r in rows]
    if limit:
        nous_list = nous_list[:limit]

    logger.info(f"Starting parallel batch keyword extraction for {len(nous_list)} NOU reports (workers={max_workers})...")

    processed = 0
    t0 = time.time()

    def process_one(row):
        nid = str(row.get("id", ""))
        title = str(row.get("title", ""))
        try:
            kws = extract_keywords_for_nou(row)
            update_nou_keywords(nid, kws, row.get("document_profile"))
            return True, nid, len(kws)
        except Exception as e:
            logger.error(f"Error processing NOU {nid}: {e}")
            return False, nid, 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_one, r) for r in nous_list]
        for f in concurrent.futures.as_completed(futures):
            success, nid, count = f.result()
            if success:
                processed += 1
            if processed % 15 == 0 or processed == len(nous_list):
                elapsed = time.time() - t0
                rate = processed / max(1.0, elapsed)
                eta_sec = (len(nous_list) - processed) / max(0.1, rate)
                logger.info(f"[{processed}/{len(nous_list)}] Processed {nid} -> {count} keywords | Speed: {rate:.1f} NOU/s | ETA: {eta_sec/60:.1f} min")

    logger.info(f"Batch keyword extraction finished! Processed {processed} NOUs in {time.time()-t0:.1f} seconds.")



if __name__ == "__main__":
    limit_arg = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_batch_keyword_extraction(limit=limit_arg)
