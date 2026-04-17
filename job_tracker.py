#!/usr/bin/env python3
"""
Job Posting Keyword Tracker
Uses the Adzuna API to track which NEW companies posted jobs mentioning a keyword
that did not appear in the previous week's results.

Setup:
  1. Get a free API key at https://developer.adzuna.com/
  2. Set your APP_ID and APP_KEY below (or use environment variables)
  3. Run manually or schedule with cron for weekly tracking

Usage:
  python3 job_tracker.py                        # run with defaults
  python3 job_tracker.py --keyword "Splunk"     # track a different keyword
  python3 job_tracker.py --country gb           # search UK jobs (default: us)
  python3 job_tracker.py --exclude "Splunk Inc" # exclude a specific employer name
"""

import os
import sys
import csv
import json
import argparse
import requests
from datetime import datetime, date

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ── Configuration ────────────────────────────────────────────────────────────
APP_ID  = os.environ.get("ADZUNA_APP_ID",  "YOUR_APP_ID_HERE")
APP_KEY = os.environ.get("ADZUNA_APP_KEY", "YOUR_APP_KEY_HERE")

DEFAULT_KEYWORD  = "Varonis"
DEFAULT_COUNTRY  = "us"
DEFAULT_EXCLUDE  = "Varonis"
DEFAULT_CSV      = "job_tracker_log.csv"
RESULTS_PER_PAGE = 50
MAX_PAGES        = 20
# ─────────────────────────────────────────────────────────────────────────────


def fetch_jobs(keyword: str, country: str, app_id: str, app_key: str, page: int = 1) -> dict:
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


def collect_all_jobs(keyword: str, country: str, app_id: str, app_key: str) -> tuple[list[dict], int]:
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


def employer_name(job: dict) -> str:
    return job.get("company", {}).get("display_name", "") or ""


def filter_jobs(jobs: list[dict], exclude_employer: str) -> list[dict]:
    if not exclude_employer:
        return jobs
    excl_lower = exclude_employer.lower()
    return [j for j in jobs if excl_lower not in employer_name(j).lower()]


def unique_companies(jobs: list[dict]) -> set[str]:
    """Return the set of unique employer names from a list of jobs."""
    return {employer_name(j) for j in jobs if employer_name(j)}


def load_previous_companies(csv_path: str) -> set[str]:
    """Read the most recent row in the CSV and return its all_companies set."""
    if not os.path.isfile(csv_path):
        return set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return set()
    raw = rows[-1].get("all_companies", "")
    if not raw:
        return set()
    return {c.strip() for c in raw.split(";") if c.strip()}


def top_states(jobs: list[dict], n: int = 10) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for j in jobs:
        areas = j.get("location", {}).get("area", [])
        if len(areas) >= 2:
            state = areas[1]
            counts[state] = counts.get(state, 0) + 1
    return sorted(counts.items(), key=lambda x: -x[1])[:n]


def append_to_csv(filepath: str, row: dict) -> None:
    fieldnames = [
        "date", "keyword", "country",
        "total_raw", "total_filtered", "excluded_count",
        "total_companies", "new_company_count",
        "new_companies", "all_companies", "top_states",
    ]
    file_exists = os.path.isfile(filepath)
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def save_detail_json(jobs: list[dict], keyword: str) -> str:
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"jobs_{keyword.lower().replace(' ', '_')}_{ts}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, default=str)
    return filename


def run(keyword: str, country: str, exclude: str, csv_path: str,
        save_json: bool, app_id: str, app_key: str) -> None:

    if "YOUR_APP_ID" in app_id or "YOUR_APP_KEY" in app_key:
        print("\n⚠️  No API credentials found.")
        print("   1. Sign up free at https://developer.adzuna.com/")
        print("   2. Set ADZUNA_APP_ID and ADZUNA_APP_KEY as environment variables, or")
        print("      edit APP_ID / APP_KEY at the top of this script.\n")
        return

    # Load previous week's companies before fetching new data
    prev_companies = load_previous_companies(csv_path)
    is_first_run   = not prev_companies

    print(f"\n🔍 Searching '{keyword}' jobs in '{country}'...")
    jobs_raw, api_total = collect_all_jobs(keyword, country, app_id, app_key)

    jobs_filtered = filter_jobs(jobs_raw, exclude)
    excluded_n    = len(jobs_raw) - len(jobs_filtered)

    curr_companies = unique_companies(jobs_filtered)
    new_companies  = curr_companies - prev_companies
    states         = top_states(jobs_filtered)

    print(f"\n📊 Results for '{keyword}' on {date.today()}")
    print(f"   API total reported   : {api_total:,}")
    print(f"   Fetched              : {len(jobs_raw):,}")
    print(f"   Excluded ('{exclude}'): {excluded_n:,}")
    print(f"   Third-party listings : {len(jobs_filtered):,}")
    print(f"   Unique companies     : {len(curr_companies):,}")

    if is_first_run:
        print(f"\n   ℹ️  First run — no previous week to compare against.")
        print(f"      All {len(curr_companies):,} companies recorded as baseline.")
    else:
        print(f"   Previous companies   : {len(prev_companies):,}")
        print(f"\n   🆕 New companies this week: {len(new_companies):,}")
        if new_companies:
            for name in sorted(new_companies):
                print(f"     + {name}")

    if states:
        print("\n   Top states:")
        for state, count in states:
            print(f"     {count:3d}  {state}")

    row = {
        "date":             date.today().isoformat(),
        "keyword":          keyword,
        "country":          country,
        "total_raw":        len(jobs_raw),
        "total_filtered":   len(jobs_filtered),
        "excluded_count":   excluded_n,
        "total_companies":  len(curr_companies),
        "new_company_count": len(new_companies) if not is_first_run else "",
        "new_companies":    "; ".join(sorted(new_companies)) if not is_first_run else "",
        "all_companies":    "; ".join(sorted(curr_companies)),
        "top_states":       "; ".join(f"{s}:{c}" for s, c in states),
    }
    append_to_csv(csv_path, row)
    print(f"\n✅ Row appended to {csv_path}")

    if save_json:
        jf = save_detail_json(jobs_filtered, keyword)
        print(f"   Full listing detail saved to {jf}")


def main():
    parser = argparse.ArgumentParser(description="Track new companies posting jobs with a keyword week-over-week.")
    parser.add_argument("--keyword",  default=DEFAULT_KEYWORD)
    parser.add_argument("--country",  default=DEFAULT_COUNTRY)
    parser.add_argument("--exclude",  default=DEFAULT_EXCLUDE)
    parser.add_argument("--csv",      default=DEFAULT_CSV)
    parser.add_argument("--json",     action="store_true")
    parser.add_argument("--app-id",   default=APP_ID)
    parser.add_argument("--app-key",  default=APP_KEY)
    args = parser.parse_args()

    run(
        keyword   = args.keyword,
        country   = args.country,
        exclude   = args.exclude,
        csv_path  = args.csv,
        save_json = args.json,
        app_id    = args.app_id,
        app_key   = args.app_key,
    )


if __name__ == "__main__":
    main()
