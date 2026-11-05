#!/usr/bin/env python3
import os
import re
import csv
import sys
import time
import argparse
import requests
import shutil
from bs4 import BeautifulSoup

# Ensure backend libraries can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
from app.lib.ingest import run_unified_ingestion, extract_metadata_fields
from app.lib.auth import is_safe_external_url

LANDING_PAGE_URL = "https://www.regjeringen.no/no/dokument/nou-ar/id1767/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
PDF_DIR = "./data/pdf"
METADATA_FILE = "nou_metadata.csv"

def sanitize_filename(name):
    """Sanitizes NOU titles for use as safe filenames on Windows and Unix."""
    cleaned = re.sub(r'[\\/*?:"<>|]', '_', name)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    if len(cleaned) > 100:
        cleaned = cleaned[:100].rstrip(' ._')
    return cleaned

def extract_id_from_url(url):
    """Extracts the unique ID from a regjeringen.no document URL (e.g. id3162501)."""
    match = re.search(r'/id(\d+)/?$', url)
    if match:
        return match.group(1)
    slug_match = re.search(r'/nou-([^/]+)/?', url)
    if slug_match:
        return slug_match.group(1)
    return re.sub(r'\W+', '', url)

def polite_request(url, headers=None, stream=False, timeout=30, max_retries=5, delay=2.0):
    """Wrapper around requests.get that handles HTTP 429 and 503 with exponential backoff and SSRF protection."""
    if not is_safe_external_url(url):
        raise ValueError(f"SSRF Protection: Blocked potentially unsafe or private network URL: {url}")
    delay_time = delay
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, stream=stream, timeout=timeout)
            if r.status_code == 429:
                print(f"Got HTTP 429 (Rate Limited). Waiting {delay_time}s and retrying (attempt {attempt+1}/{max_retries})...")
                time.sleep(delay_time)
                delay_time *= 2
                continue
            elif r.status_code == 503:
                print(f"Got HTTP 503 (Service Unavailable). Waiting {delay_time}s and retrying (attempt {attempt+1}/{max_retries})...")
                time.sleep(delay_time)
                delay_time *= 2
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise
            print(f"Network error ({e}). Waiting {delay_time}s and retrying (attempt {attempt+1}/{max_retries})...")
            time.sleep(delay_time)
            delay_time *= 2

def resolve_metadata_from_regjeringen(nou_id_or_url, delay=2.0):
    """
    Crawls regjeringen.no to find NOU metadata (id, title, year, source_url) 
    for the given ID or Landing Page URL.
    """
    headers = {"User-Agent": USER_AGENT}
    
    # 1. Determine target ID and target URL
    target_id = None
    target_url = None
    
    if nou_id_or_url.startswith("http"):
        target_url = nou_id_or_url
        target_id = extract_id_from_url(nou_id_or_url)
    else:
        target_id = nou_id_or_url
        
    print(f"Resolving NOU metadata from Regjeringen.no (Target ID: {target_id})...")
    
    # 2. Search NOU landing list pages for the metadata (only if direct target_url was NOT provided)
    page_num = 0 if not target_url else 6
    found_meta = None
    
    while page_num < 6:  # search first 6 pages (recent years)
        page_url = LANDING_PAGE_URL if page_num == 0 else f"{LANDING_PAGE_URL}?page={page_num}"
        print(f"Searching list page {page_num}: {page_url}...")
        try:
            r = polite_request(page_url, headers=headers, timeout=20, delay=delay)
        except Exception as e:
            print(f"Failed to fetch list page {page_num}: {e}")
            break
            
        soup = BeautifulSoup(r.text, 'html.parser')
        links_found = 0
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = re.sub(r'\s+', ' ', a.get_text()).strip()
            
            if ('nou-' in href.lower() or '/dokumenter/nou' in href.lower()) and 'id' in href.lower() and re.search(r'NOU\s+\d{4}', text):
                detail_url = href
                if href.startswith("/"):
                    detail_url = "https://www.regjeringen.no" + href
                    
                item_id = extract_id_from_url(detail_url)
                if item_id == target_id:
                    year_match = re.search(r'NOU\s+(\d{4})', text)
                    item_year = int(year_match.group(1)) if year_match else 2026
                    found_meta = {
                        "id": target_id,
                        "title": text,
                        "year": item_year,
                        "source_url": detail_url
                    }
                    print(f"Found match in list: '{text}' at {detail_url}")
                    break
                links_found += 1
                
        if found_meta or links_found == 0:
            break
        page_num += 1
        time.sleep(0.5)
        
    # 3. Fallback: if not found on the list page but we have a detail page URL, fetch it directly
    if not found_meta and target_url:
        print(f"ID not found in list pagination. Fetching detail page directly: {target_url}")
        try:
            r = polite_request(target_url, headers=headers, timeout=20, delay=delay)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Extract title from h1 or page title
            h1 = soup.find('h1')
            title_text = h1.get_text().strip() if h1 else "NOU 2026: Unknown"
            
            # Try to extract year
            year_match = re.search(r'20\d{2}', title_text)
            item_year = int(year_match.group(0)) if year_match else 2026
            
            found_meta = {
                "id": target_id,
                "title": title_text,
                "year": item_year,
                "source_url": target_url
            }
        except Exception as e:
            print(f"Failed to fetch detail page directly: {e}")
            
    return found_meta

def fetch_pdf_url_from_detail_page(detail_url, delay=2.0):
    """Parses the detail page to locate the direct PDF download link."""
    headers = {"User-Agent": USER_AGENT}
    try:
        r = polite_request(detail_url, headers=headers, timeout=20, delay=delay)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        pdf_link = None
        # First pass: "dokumentet i pdf" in link text
        for a in soup.find_all("a", href=True):
            a_href = a["href"]
            a_text = a.get_text().lower()
            if a_href.endswith(".pdf") and "dokumentet i pdf" in a_text:
                pdf_link = a_href
                break
                
        # Second pass: any PDF link containing "pdf" in text
        if not pdf_link:
            for a in soup.find_all("a", href=True):
                a_href = a["href"]
                a_text = a.get_text().lower()
                if a_href.endswith(".pdf") and "pdf" in a_text:
                    pdf_link = a_href
                    break
                    
        # Third pass: first link ending with pdf
        if not pdf_link:
            for a in soup.find_all("a", href=True):
                a_href = a["href"]
                if a_href.endswith(".pdf"):
                    pdf_link = a_href
                    break
                    
        if pdf_link:
            if pdf_link.startswith("/"):
                pdf_link = "https://www.regjeringen.no" + pdf_link
            return pdf_link
    except Exception as e:
        print(f"Error parsing detail page PDF link: {e}")
        
    return None

def download_file(url, output_path, delay=2.0):
    """Downloads a file politey."""
    headers = {"User-Agent": USER_AGENT}
    try:
        r = polite_request(url, headers=headers, stream=True, timeout=60, delay=delay)
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"Failed to download PDF from {url}: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return False

def update_metadata_csv(meta):
    """Updates/inserts NOU metadata record in nou_metadata.csv."""
    existing_records = {}
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_records[row["id"]] = row
                
    # Update or add new record
    existing_records[meta["id"]] = {
        "id": meta["id"],
        "title": meta["title"],
        "year": str(meta["year"]),
        "pdf_url": meta["pdf_url"],
        "source_url": meta.get("source_url") or ""
    }
    
    with open(METADATA_FILE, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "title", "year", "pdf_url", "source_url"])
        for r in existing_records.values():
            writer.writerow([r.get("id"), r.get("title"), r.get("year"), r.get("pdf_url"), r.get("source_url")])
    print(f"Updated metadata CSV file: {METADATA_FILE}")

def process_single_nou(
    nou_input: str,
    source_url: str = None,
    nou_id: str = None,
    title: str = None,
    year: int = None,
    force: bool = False,
    generate_podcast: bool = True,
    delay: float = 2.0
) -> bool:
    """
    Ingests a single NOU given an ID, regjeringen.no URL, direct PDF URL, or local PDF path.
    Resolves metadata, downloads PDF, extracts cover & page count, chunks text, generates embeddings,
    saves metadata & chunks, populates document_profile & nou_authors, maps 2-tier taxonomy, generates podcast audio, and updates system statistics.
    """
    # Pre-check: Verify DB existence if not force
    if not force:
        candidate_check_id = nou_id or extract_id_from_url(nou_input)
        if candidate_check_id:
            try:
                from app.lib import db
                existing = db.get_nou(candidate_check_id)
                if existing:
                    print(f"NOU ID '{candidate_check_id}' ('{existing.get('title')}') ALREADY exists in database. Skipping duplicate ingestion.")
                    return True
            except Exception as e:
                pass

    os.makedirs(PDF_DIR, exist_ok=True)
    pdf_url = None
    pdf_path = None
    
    # CASE 1: Local PDF File
    if os.path.exists(nou_input) and nou_input.endswith(".pdf"):
        print(f"Detected input as local PDF file: {nou_input}")
        if not nou_id:
            basename = os.path.basename(nou_input)
            match = re.match(r"^(\d+)", basename)
            nou_id = match.group(1) if match else os.path.splitext(basename)[0]
            
        if not title:
            basename = os.path.basename(nou_input)
            title_part = re.sub(r"^\d+_", "", basename)
            title = os.path.splitext(title_part)[0].replace("_", " ")
            
        if not year:
            year = 2026
            
        pdf_path = os.path.join(PDF_DIR, f"{nou_id}_{sanitize_filename(title)}.pdf")
        shutil.copy2(nou_input, pdf_path)
        pdf_url = f"file:///{os.path.abspath(pdf_path).replace(os.sep, '/')}"
        print(f"Copied PDF file to {pdf_path}")
        
    # CASE 2: Direct PDF URL
    elif nou_input.startswith("http") and nou_input.endswith(".pdf"):
        print(f"Detected input as direct PDF URL: {nou_input}")
        if not nou_id:
            nou_id = extract_id_from_url(nou_input)
            
        if not title:
            title = f"NOU Document {nou_id}"
            
        if not year:
            year = 2026
            
        pdf_path = os.path.join(PDF_DIR, f"{nou_id}_{sanitize_filename(title)}.pdf")
        print(f"Downloading PDF from {nou_input}...")
        if not download_file(nou_input, pdf_path, delay=delay):
            print("Error: Failed to download PDF. Aborting.")
            return False
        pdf_url = nou_input
        
    # CASE 3: Regjeringen Landing Page URL or NOU ID
    else:
        meta = resolve_metadata_from_regjeringen(nou_input, delay=delay)
        if not meta:
            print("Error: Could not resolve NOU metadata from Regjeringen.no.")
            return False
            
        nou_id = nou_id or meta["id"]
        title = title or meta["title"]
        year = year or meta["year"]
        source_url = source_url or meta["source_url"]
        
        print("Resolving PDF link from detail page...")
        pdf_url = fetch_pdf_url_from_detail_page(source_url, delay=delay)
        pdf_path = None
        if not pdf_url:
            print(f"Warning: No PDF link found on landing page ({source_url}), falling back to native HTML chapter scraping...")
            pdf_url = ""
        else:
            pdf_path = os.path.join(PDF_DIR, f"{nou_id}_{sanitize_filename(title)}.pdf")
            if os.path.exists(pdf_path) and not force:
                print(f"PDF already downloaded: {pdf_path}. Use --force to download again.")
            else:
                print(f"Downloading NOU PDF: {pdf_url} -> {pdf_path}...")
                if not download_file(pdf_url, pdf_path, delay=delay):
                    print("Warning: Failed to download PDF. Falling back to native HTML chapter scraping...")
                    pdf_path = None
                    pdf_url = ""
                    
        update_metadata_csv({
            "id": nou_id,
            "title": title,
            "year": year,
            "pdf_url": pdf_url,
            "source_url": source_url
        })
        
    print("\n--- Running Unified Ingestion Pipeline ---")
    return run_unified_ingestion(
        pdf_path=pdf_path,
        nou_id=nou_id,
        title=title,
        year=year,
        pdf_url=pdf_url,
        source_url=source_url,
        generate_podcast=generate_podcast
    )

def main():
    parser = argparse.ArgumentParser(description="Unified NOU Ingestion Utility")
    parser.add_argument(
        "nou_input",
        help="NOU ID (e.g. 3162501), Regjeringen URL, direct PDF URL, or local PDF path"
    )
    parser.add_argument("--id", help="Explicit NOU ID (fallback/override)")
    parser.add_argument("--title", help="Explicit NOU Title (fallback/override)")
    parser.add_argument("--year", type=int, help="Explicit NOU Year (fallback/override)")
    parser.add_argument("--source-url", help="Explicit landing page URL (fallback/override)")
    parser.add_argument("--force", action="store_true", help="Force ingestion even if already indexed")
    parser.add_argument("--skip-podcast", action="store_true", help="Skip automatic podcast audio generation")
    parser.add_argument("--delay", type=float, default=2.0, help="Download/polite delay in seconds")
    
    args = parser.parse_args()
    
    success = process_single_nou(
        nou_input=args.nou_input.strip(),
        source_url=args.source_url,
        nou_id=args.id,
        title=args.title,
        year=args.year,
        force=args.force,
        generate_podcast=not args.skip_podcast,
        delay=args.delay
    )
    
    if success:
        print("\n=== SUCCESS ===")
        print("Ingestion finished successfully.")
        sys.exit(0)
    else:
        print("\n=== FAILURE ===")
        print("Unified ingestion pipeline failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()

