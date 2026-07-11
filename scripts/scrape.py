#!/usr/bin/env python3
"""
Scrapes every General Election race for a given year from
electionstats.state.ma.us and downloads precinct-level results as CSV.

Usage:
    pip install requests beautifulsoup4
    python scrape.py 2024
    python scrape.py 2022
    python scrape.py 2020
    python scrape.py 2018

    (defaults to 2024 if no year is given)

Output:
    ../data/<year>/<Office>/<District>.csv   (precinct-level results)
    ../data/<year>/manifest.csv              (index of every race + status)

Notes:
    - This hits electionstats.state.ma.us directly. Be polite: there's a
      built-in delay between requests (REQUEST_DELAY_SECONDS below).
    - The search results page appears to paginate/lazy-load past a certain
      row count. This script tries several strategies to make sure it finds
      every race:
        1. Walks the "All Offices" search page and follows any pagination
           links it finds.
        2. As a fallback/cross-check, also walks the search page once per
           known office category (so each request returns a smaller,
           more complete result set).
      IDs found by either method are merged and deduplicated before
      downloading, so it's safe for both to run.
    - If you find races are missing after running this, open an issue with
      the printed "office categories found on page" output so the office
      list below can be corrected/extended.
"""

import csv
import os
import re
import time
import sys
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

YEAR = sys.argv[1] if len(sys.argv) > 1 else "2024"

BASE = "https://electionstats.state.ma.us"
SEARCH_URL = f"{BASE}/elections/search/year_from:{YEAR}/year_to:{YEAR}/stage:General"
DOWNLOAD_URL = f"{BASE}/elections/download/{{id}}/precincts_include:1/"
VIEW_URL_RE = re.compile(r"/elections/view/(\d+)")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", YEAR)
REQUEST_DELAY_SECONDS = 1.0
HEADERS = {"User-Agent": "Mozilla/5.0 (research script; contact: n/a)"}

# Known office categories from the site's own filter dropdown.
# Used as a fallback pass to make sure large offices (State Rep, State
# Senate, etc.) aren't cut off by any pagination/row limit on the
# "All Offices" view.
OFFICE_NAMES = [
    "President", "U.S. Senate", "U.S. House",
    "Governor", "Lieutenant Governor", "Attorney General",
    "Secretary of the Commonwealth", "Treasurer", "Auditor",
    "Governor's Council", "State Senate", "State Representative",
    "Party State Committee Man", "Party State Committee Woman",
    "Delegate to the National Convention",
    "Alternate Delegate to the National Convention",
    "District Attorney", "Clerk of Courts",
    "Clerk of Superior Court (Civil)", "Clerk of Superior Court (Criminal)",
    "Clerk of Supreme Judicial Court", "County Charter Commission",
    "Register of Deeds", "Sheriff", "County Treasurer",
    "Probate Judge", "Register of Probate",
    "Council of Governments Executive Committee",
]


def get_soup(url):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def find_pagination_links(soup, current_url):
    """Look for common pagination patterns and return absolute URLs."""
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = (a.get_text() or "").strip().lower()
        if "page" in href.lower() or text in ("next", "next »", "»", ">"):
            links.add(urljoin(current_url, href))
    return links


def extract_races(soup):
    """
    Pulls (election_id, office, district) tuples out of a search results
    table. Falls back to just election_id if office/district can't be
    determined from row context.
    """
    races = []
    seen_ids = set()
    for row in soup.find_all("tr"):
        row_text = row.get_text(" ", strip=True)
        m = VIEW_URL_RE.search(str(row))
        if not m:
            continue
        election_id = m.group(1)
        if election_id in seen_ids:
            continue
        seen_ids.add(election_id)
        cells = row.find_all("td")
        office = cells[1].get_text(strip=True) if len(cells) > 1 else "Unknown Office"
        district = cells[2].get_text(strip=True) if len(cells) > 2 else "Unknown District"
        races.append((election_id, office, district))
    return races


def crawl_all_offices():
    """Primary pass: walk the all-offices search page + any pagination."""
    all_races = {}
    to_visit = [SEARCH_URL]
    visited = set()
    while to_visit:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)
        print(f"  fetching {url}")
        try:
            soup = get_soup(url)
        except requests.RequestException as e:
            print(f"    ! failed: {e}")
            continue
        for election_id, office, district in extract_races(soup):
            all_races[election_id] = (office, district)
        for link in find_pagination_links(soup, url):
            if link not in visited:
                to_visit.append(link)
        time.sleep(REQUEST_DELAY_SECONDS)
    return all_races


def crawl_by_office(office_name):
    """Fallback pass: search scoped to a single office name via query string."""
    url = f"{SEARCH_URL}/office:{requests.utils.quote(office_name)}"
    try:
        soup = get_soup(url)
    except requests.RequestException as e:
        print(f"    ! failed for office '{office_name}': {e}")
        return {}
    races = {}
    for election_id, office, district in extract_races(soup):
        races[election_id] = (office or office_name, district)
    return races


def sanitize(name):
    return re.sub(r"[^A-Za-z0-9._ -]", "", name).strip().replace(" ", "_")


def download_precinct_csv(election_id, office, district):
    url = DOWNLOAD_URL.format(id=election_id)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        return None, str(e)

    office_dir = os.path.join(OUTPUT_DIR, sanitize(office) or "Unknown_Office")
    os.makedirs(office_dir, exist_ok=True)
    filename = f"{sanitize(district) or election_id}_{election_id}.csv"
    filepath = os.path.join(office_dir, filename)
    with open(filepath, "wb") as f:
        f.write(resp.content)
    return filepath, None


def main():
    print("Pass 1: crawling all-offices search page (+ pagination)...")
    races = crawl_all_offices()
    print(f"  found {len(races)} races so far")

    print("Pass 2: crawling per-office as a cross-check...")
    for office_name in OFFICE_NAMES:
        print(f"  office: {office_name}")
        found = crawl_by_office(office_name)
        for eid, val in found.items():
            races.setdefault(eid, val)
        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"\nTotal unique races found: {len(races)}")
    if len(races) == 0:
        print("No races found — the site's HTML structure may not match this "
              "script's assumptions. Save a sample page with "
              "`curl -A 'Mozilla/5.0' <search url> -o sample.html` and inspect "
              "it, or share it so the parser can be fixed.")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    manifest_path = os.path.join(OUTPUT_DIR, "manifest.csv")
    with open(manifest_path, "w", newline="", encoding="utf-8") as mf:
        writer = csv.writer(mf)
        writer.writerow(["election_id", "office", "district", "status", "filepath"])

        for i, (election_id, (office, district)) in enumerate(races.items(), 1):
            print(f"[{i}/{len(races)}] {office} - {district} ({election_id})")
            filepath, error = download_precinct_csv(election_id, office, district)
            status = "ok" if filepath else f"error: {error}"
            writer.writerow([election_id, office, district, status,
                              os.path.relpath(filepath, OUTPUT_DIR) if filepath else ""])
            time.sleep(REQUEST_DELAY_SECONDS)

    print(f"\nDone. Manifest written to {manifest_path}")


if __name__ == "__main__":
    main()
