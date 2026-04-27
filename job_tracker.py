#!/usr/bin/env python3
"""
Job Posting Keyword Tracker
Uses the Adzuna API to track which NEW companies posted jobs mentioning a keyword
that did not appear in the previous week's results. Runs for all configured keywords.

Setup:
  Set ADZUNA_APP_ID and ADZUNA_APP_KEY as environment variables (or GitHub Actions secrets).

Usage:
  python3 job_tracker.py                     # run all keywords
  python3 job_tracker.py --keyword "Splunk"  # run a single keyword
"""

import os
import re
import sys
import csv
import json
import argparse
import requests
from datetime import datetime, date

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ── Configuration ─────────────────────────────────────────────────────────────
APP_ID  = os.environ.get("ADZUNA_APP_ID",  "YOUR_APP_ID_HERE")
APP_KEY = os.environ.get("ADZUNA_APP_KEY", "YOUR_APP_KEY_HERE")

# (keyword to search, employer substring to exclude)
KEYWORDS = [
    ("Varonis",   "Varonis"),
    ("Dynatrace", "Dynatrace"),
    ("LiveRamp",  "LiveRamp"),
    ("nCino",     "nCino"),
    ("JFrog",     "JFrog"),
    ("Guidewire", "Guidewire"),
    ("Agilysys",  "Agilysys"),
    ("Qualys",    "Qualys"),
]

DEFAULT_COUNTRY  = "us"
DEFAULT_CSV      = "job_tracker_log.csv"
RESULTS_PER_PAGE = 50
MAX_PAGES        = 20
# ──────────────────────────────────────────────────────────────────────────────


def fetch_jobs(keyword, country, app_id, app_key, page=1):
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
    params = {
        "app_id":           app_id,
        "app_key":          app_key,
        "what":             keyword,
        "results_per_page": RESULTS_PER_PAGE,
        "content-type":     "application/json",
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def collect_all_jobs(keyword, country, app_id, app_key):
    all_jobs = []

    print(f"  Fetching page 1...", end="", flush=True)
    first = fetch_jobs(keyword, country, app_id, app_key, page=1)
    total = first.get("count", 0)
    all_jobs.extend(first.get("results", []))
    print(f" {len(all_jobs)}/{total}")

    max_pages = min(MAX_PAGES, -(-total // RESULTS_PER_PAGE))
    for page in range(2, max_pages + 1):
        if len(all_jobs) >= total:
            break
        print(f"  Fetching page {page}...", end="", flush=True)
        data = fetch_jobs(keyword, country, app_id, app_key, page=page)
        results = data.get("results", [])
        if not results:
            break
        all_jobs.extend(results)
        print(f" {len(all_jobs)}/{total}")

    return all_jobs, total


def employer_name(job):
    return (job.get("company", {}).get("display_name", "") or "").strip()


def filter_jobs(jobs, exclude_employer):
    if not exclude_employer:
        return jobs
    excl_lower = exclude_employer.lower()
    return [j for j in jobs if excl_lower not in employer_name(j).lower()]


def unique_companies(jobs):
    return {employer_name(j) for j in jobs if employer_name(j)}


_SUFFIX_RE = re.compile(
    r'[\s,]+(Inc\.?|LLC\.?|Ltd\.?|L\.L\.C\.?|Corp\.?|Corporation|Holdings?|'
    r'Incorporated|Limited|LLP|LP|PLC|AG|GmbH|N\.A\.?|& Co\.?|Bank)$',
    re.IGNORECASE,
)


def _normalize(name):
    """Lowercase + strip trailing legal suffixes for lookalike comparison."""
    name = name.strip().lower()
    prev = None
    while prev != name:
        prev = name
        name = _SUFFIX_RE.sub('', name).strip().rstrip(',').strip()
    return name


def canonicalize_companies(companies):
    """
    Collapse near-duplicate names within a set by:
    1. Merging names with the same normalized base (e.g. 'Foo Holdings' == 'Foo Inc.')
    2. Absorbing names where a shorter normalized name is a word-level prefix
       (e.g. 'HD Supply' absorbs 'HD Supply Management')
    The shortest original name is kept as canonical.
    """
    pairs = sorted([(c, _normalize(c)) for c in companies], key=lambda x: len(x[0]))
    accepted = []  # list of (original, normalized)
    for orig, norm in pairs:
        absorbed = False
        for _, cn in accepted:
            if norm == cn:
                absorbed = True
                break
            remainder = norm[len(cn):]
            if remainder and norm.startswith(cn) and remainder[0] in (' ', ',', '.', '-'):
                absorbed = True
                break
        if not absorbed:
            accepted.append((orig, norm))
    return {orig for orig, _ in accepted}


def build_company_url_map(jobs):
    """Return {employer_name: redirect_url} using the first posting seen per company."""
    result = {}
    for j in jobs:
        name = employer_name(j)
        if name and name not in result:
            result[name] = j.get("redirect_url", "") or ""
    return result


def load_previous_companies(csv_path, keyword):
    """Return all companies ever seen for this keyword across all historical runs."""
    if not os.path.isfile(csv_path):
        return set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    keyword_rows = [r for r in rows if r.get("keyword", "").lower() == keyword.lower()]
    if not keyword_rows:
        return set()
    all_seen = set()
    for row in keyword_rows:
        raw = row.get("all_companies", "")
        if raw:
            all_seen.update(c.strip() for c in raw.split(";") if c.strip())
    return all_seen


def append_to_csv(filepath, row):
    fieldnames = [
        "date", "keyword", "country",
        "total_raw", "total_filtered", "excluded_count",
        "total_companies", "new_company_count",
        "new_companies", "all_companies",
    ]
    file_exists = os.path.isfile(filepath)
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def run_keyword(keyword, exclude, country, csv_path, app_id, app_key):
    prev_companies = load_previous_companies(csv_path, keyword)
    is_first_run   = not prev_companies

    print(f"\n--- {keyword} ---")
    jobs_raw, api_total = collect_all_jobs(keyword, country, app_id, app_key)

    jobs_filtered   = filter_jobs(jobs_raw, exclude)
    excluded_n      = len(jobs_raw) - len(jobs_filtered)
    url_map         = build_company_url_map(jobs_filtered)
    curr_companies  = canonicalize_companies(unique_companies(jobs_filtered))
    prev_normalized = {_normalize(c) for c in prev_companies}
    new_companies   = {c for c in curr_companies if _normalize(c) not in prev_normalized}

    print(f"  Fetched: {len(jobs_raw):,}  |  Third-party: {len(jobs_filtered):,}  |  Unique companies: {len(curr_companies):,}")

    if is_first_run:
        print(f"  First run — {len(curr_companies):,} companies recorded as baseline.")
    else:
        print(f"  New companies this week: {len(new_companies):,}")
        for name in sorted(new_companies):
            url = url_map.get(name, "")
            print(f"    + {name}" + (f"  {url}" if url else ""))

    def fmt_new_company(name):
        url = url_map.get(name, "")
        return f"{name}|{url}" if url else name

    row = {
        "date":              date.today().isoformat(),
        "keyword":           keyword,
        "country":           country,
        "total_raw":         len(jobs_raw),
        "total_filtered":    len(jobs_filtered),
        "excluded_count":    excluded_n,
        "total_companies":   len(curr_companies),
        "new_company_count": len(new_companies) if not is_first_run else "",
        "new_companies":     "; ".join(fmt_new_company(c) for c in sorted(new_companies)) if not is_first_run else "",
        "all_companies":     "; ".join(sorted(curr_companies)),
    }
    append_to_csv(csv_path, row)


def main():
    parser = argparse.ArgumentParser(description="Track new companies posting jobs with a keyword week-over-week.")
    parser.add_argument("--keyword", default=None,           help="Run a single keyword (default: run all)")
    parser.add_argument("--exclude", default=None,           help="Employer to exclude (required if --keyword is set)")
    parser.add_argument("--country", default=DEFAULT_COUNTRY)
    parser.add_argument("--csv",     default=DEFAULT_CSV)
    parser.add_argument("--app-id",  default=APP_ID)
    parser.add_argument("--app-key", default=APP_KEY)
    args = parser.parse_args()

    if "YOUR_APP_ID" in args.app_id or "YOUR_APP_KEY" in args.app_key:
        print("\nNo API credentials found.")
        print("  Set ADZUNA_APP_ID and ADZUNA_APP_KEY as environment variables or GitHub Actions secrets.\n")
        return

    if args.keyword:
        exclude = args.exclude or args.keyword
        run_keyword(args.keyword, exclude, args.country, args.csv, args.app_id, args.app_key)
    else:
        for keyword, exclude in KEYWORDS:
            run_keyword(keyword, exclude, args.country, args.csv, args.app_id, args.app_key)

    print(f"\nDone. Results appended to {args.csv}")


if __name__ == "__main__":
    main()
