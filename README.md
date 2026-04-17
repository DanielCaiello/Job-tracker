# Job Posting Keyword Tracker

Tracks third-party job listings mentioning a keyword (e.g. "Varonis") over time,
excluding listings posted by the keyword company itself. Logs weekly snapshots
to a CSV you can chart in Excel or Google Sheets.

---

## Quick Start

### 1. Get a free Adzuna API key
Sign up at **https://developer.adzuna.com/** — it's free with no credit card required.
You'll get an **App ID** and an **App Key**.

### 2. Set your credentials

**Option A — environment variables (recommended)**
```bash
export ADZUNA_APP_ID="abc123"
export ADZUNA_APP_KEY="xyz789abc123..."
```
Add these lines to your `~/.zshrc` or `~/.bashrc` to make them permanent.

**Option B — edit the script directly**
Open `job_tracker.py` and replace the placeholders near the top:
```python
APP_ID  = "abc123"
APP_KEY = "xyz789abc123..."
```

### 3. Run it
```bash
python3 job_tracker.py
```

That's it. Results print to the terminal and a row is appended to `job_tracker_log.csv`.

---

## Command-Line Options

| Flag | Default | Description |
|------|---------|-------------|
| `--keyword` | `Varonis` | Keyword to search for in job listings |
| `--country` | `us` | Country: `us`, `gb`, `ca`, `au`, `de`, `fr`, `in`, `nl`, `nz`, `sg`, `za` |
| `--exclude` | `Varonis` | Filter out listings from employers containing this string |
| `--csv` | `job_tracker_log.csv` | CSV log file to append results to |
| `--json` | off | Also save full listing detail to a timestamped JSON file |
| `--app-id` | env/config | Override App ID at runtime |
| `--app-key` | env/config | Override App Key at runtime |

**Examples:**
```bash
# Track Varonis in the UK
python3 job_tracker.py --country gb

# Track a competitor keyword
python3 job_tracker.py --keyword "CrowdStrike" --exclude "CrowdStrike"

# Save full job detail for deeper analysis
python3 job_tracker.py --json
```

---

## Scheduling Weekly Runs (Mac/Linux)

Edit your crontab:
```bash
crontab -e
```

Add this line to run every Monday at 8am:
```
0 8 * * 1 /path/to/weekly_tracker.sh >> /path/to/tracker.log 2>&1
```

Or if you prefer to run the Python script directly:
```
0 8 * * 1 cd /path/to/tracker && ADZUNA_APP_ID=abc123 ADZUNA_APP_KEY=xyz789 python3 job_tracker.py
```

---

## CSV Output

Each run appends one row to `job_tracker_log.csv`:

| Column | Description |
|--------|-------------|
| `date` | Date of the run (YYYY-MM-DD) |
| `keyword` | Keyword searched |
| `country` | Country code |
| `total_raw` | Listings fetched before filtering |
| `total_filtered` | Third-party listings (after excluding the vendor) |
| `excluded_count` | Number of vendor-own listings removed |
| `top_employers` | Top 15 hiring employers and counts |
| `top_states` | Top 10 US states by listing count |

After a few weeks of runs, `total_filtered` over time gives you the trend line.

---

## Tracking Multiple Keywords

In `weekly_tracker.sh`, uncomment and add extra lines:
```bash
python3 job_tracker.py --keyword "Varonis"     --exclude "Varonis"
python3 job_tracker.py --keyword "CrowdStrike" --exclude "CrowdStrike"
python3 job_tracker.py --keyword "Splunk"      --exclude "Splunk"
```
All rows go to the same CSV — use the `keyword` column to filter in a pivot table.

---

## Adzuna Free Tier Limits

- **1,000 calls/month** on the free plan
- Each tracker run uses roughly `ceil(total_results / 50)` calls
- For Varonis (~200–400 US results), that's ~5–8 calls per run
- Running weekly for 4 keywords = ~160 calls/month — well within the free tier

---

## Notes

- Adzuna aggregates listings from Indeed, LinkedIn, company sites, and others —
  so it's a broad proxy, not a single-source count.
- Employer name matching is substring-based and case-insensitive.
  If a staffing agency posts a Varonis role, it won't be excluded (by design —
  those are genuine third-party demand signals).
- For UK-specific data, `--country gb` gives you the same market that
  IT Jobs Watch tracks.
