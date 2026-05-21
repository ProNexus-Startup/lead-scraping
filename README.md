# Pronexus Lead Scraping Pipeline

An automated pipeline that collects business leads from Google Maps, crawls their websites, and uses an LLM to extract owner name and contact emails — exported to a clean CSV.

**Flow:** Google Maps (RapidAPI) → Website Crawl → LLM Extraction → CSV

---

## Project Structure

```
lead-scraping/
├── config/
│   └── settings.py              # All configuration loaded from .env
├── data/
│   └── us-zip-codes.csv         # 40k+ US ZIP codes with population data
├── src/
│   ├── models/lead.py           # Lead dataclass — contract between all pipeline stages
│   ├── scrapers/
│   │   ├── maps_scraper.py      # RapidAPI Google Maps integration
│   │   ├── web_crawler.py       # Same-domain BFS website crawler with optional Playwright fallback
│   │   └── zip_loader.py        # Loads and filters ZIP codes by state / population
│   ├── extractors/
│   │   └── llm_extractor.py     # LLM prompt, JSON schema enforcement, response parsing
│   ├── pipeline/
│   │   └── lead_pipeline.py     # Orchestrates scrape → crawl → extract → CSV
│   └── utils/
│       ├── logger.py            # ISO 8601 UTC logger (console + daily file)
│       ├── csv_writer.py        # CSV write, append, and init helpers
│       ├── progress_tracker.py  # Stop/resume state saved to progress/*.json
│       └── run_summary.py       # Quality metrics printed after each run
├── tests/                       # Unit tests (no network or API keys required)
├── output/                      # Generated CSV files
├── logs/                        # Daily log files (run_YYYYMMDD.log)
├── progress/                    # ZIP run progress files (for --resume)
├── .env.example                 # Environment variable template
├── requirements.txt
└── main.py                      # CLI entry point
```

---

## Setup

**Prerequisites:** Python 3.11+, a RapidAPI account with the [Maps Data API](https://rapidapi.com/alexanderxbx/api/maps-data) subscription, and at least one LLM API key (Groq or Cerebras).

**1. Create and activate a virtual environment**

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Configure environment variables**

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```env
RAPIDAPI_KEY=your_rapidapi_key
GROQ_API_KEY=your_groq_api_key

# Optional — only needed if using Cerebras
CEREBRAS_API_KEY=your_cerebras_api_key
LLM_PROVIDER=cerebras
```

**4. (Optional) Install Playwright for JS-rendered sites**

If you want the crawler to fall back to a headless browser for sites that require JavaScript to load content, run these two commands once:

```bash
playwright install chromium
```

Then enable the fallback in `.env`:

```env
CRAWL_PLAYWRIGHT_FALLBACK=true
```

---

## Usage

### Quick test (single lead)

```bash
python main.py --query "plumbers in Austin TX" --limit 1
```

### Direct query — specific city or area

```bash
python main.py --query "dentists in Chicago IL" --limit 20 --label dentists_chicago
```

### ZIP code mode — full state coverage

Searches every ZIP code in a state individually for complete geographic coverage.

```bash
# All ZIPs in Texas with population >= 1,000 (default)
python main.py --query "dentists" --state TX --limit 5

# Only high-population ZIPs in California
python main.py --query "pizza restaurant" --state CA --min-pop 5000 --limit 3

# Specific ZIP codes only
python main.py --query "gym" --zips 90210,90401,91101 --limit 5
```

### Stop and resume a long run

Hit `Ctrl+C` at any time — progress is saved after every ZIP. Resume with:

```bash
python main.py --query "dentists" --state TX --limit 5 --resume
```

The pipeline picks up exactly where it left off. No ZIPs are re-scraped, no API calls are wasted.

### All CLI flags

| Flag | Shorthand | Default | Description |
|------|-----------|---------|-------------|
| `--query` | `-q` | *(required)* | Business type to search, e.g. `"plumbers"` |
| `--limit` | | `1` | Leads per ZIP (ZIP mode) or total leads (direct mode) |
| `--label` | | *(empty)* | Optional suffix added to the output CSV filename |
| `--state` | `-s` | | 2-letter US state code — searches all ZIPs in that state |
| `--zips` | `-z` | | Comma-separated ZIP codes to search |
| `--min-pop` | | `1000` | Minimum ZIP population filter (use with `--state`) |
| `--resume` | | `false` | Resume a previous ZIP run from where it stopped |

---

## Output

### CSV columns

| Column | Description |
|--------|-------------|
| `business_name` | Business name from Google Maps |
| `business_name_normalized` | Name with legal suffixes removed (Inc., LLC, etc.) for outreach copy |
| `category` | Business category (e.g. Plumber, Dentist) |
| `phone` | Phone number |
| `address` | Full address |
| `website` | Business website URL |
| `rating` | Google Maps star rating |
| `reviews_count` | Number of Google reviews |
| `owner_first_name` | First name only — for personalised outreach ("Hi John,") |
| `owner_last_name` | Last name |
| `owner_name` | Full name as seen on the website |
| `owner_source_page` | URL of the page where the owner name was found |
| `owner_evidence_text` | Exact quote from the site identifying the owner |
| `email_owner_personal` | Email directly linked to the owner (e.g. john@company.com) |
| `email_owner_personal_source` | URL where the personal email was found |
| `email_owner_likely` | Probably the owner's email (e.g. smithsplumbing@gmail.com) |
| `email_owner_likely_source` | URL where the likely email was found |
| `email_generic` | Shared inbox email (info@, contact@, hello@, etc.) |
| `email_generic_source` | URL where the generic email was found |
| `email_other` | Any remaining emails found, comma-separated |
| `recommended_email` | LLM's single best pick for outreach |
| `recommended_email_type` | Category of recommended email: `owner_personal`, `owner_likely`, `generic`, or `other` |
| `owner_candidates` | JSON array of all named candidates when ownership is ambiguous |
| `llm_confidence` | `high`, `medium`, or `low` |
| `llm_reasoning` | One-sentence explanation of the LLM's decision |
| `scraped_at` | UTC timestamp of when the lead was scraped |
| `status` | `success` (owner name + at least one email found), `no_website`, `crawl_failed`, or `llm_failed` |

### Progress and summary

After each run, two files are written alongside the CSV:
- `output/*_summary.json` — quality metrics (success rate, email fill rate, confidence breakdown)
- `progress/{label}.json` — ZIP-level progress used for stop/resume

---

## LLM Providers

The pipeline supports three providers. Set `LLM_PROVIDER` in `.env` to switch.

| Provider | Env var | Default model | Notes |
|----------|---------|---------------|-------|
| Groq | `GROQ_API_KEY` | `openai/gpt-oss-120b` | Default. JSON schema supported on OSS models. |
| Cerebras | `CEREBRAS_API_KEY` | `llama-3.3-70b` | Full JSON schema support. |
| Local | `LOCAL_LLM_BASE_URL` | `openai/gpt-oss-120b` | Self-hosted via vLLM. No rate limits. |

**Switching providers:**

```env
# Groq (default)
LLM_PROVIDER=groq
GROQ_MODEL=openai/gpt-oss-120b

# Cerebras
LLM_PROVIDER=cerebras
CEREBRAS_MODEL=llama-3.3-70b

# Local / GPU (vLLM)
LLM_PROVIDER=local
LOCAL_LLM_BASE_URL=http://127.0.0.1:18000/v1
LOCAL_LLM_MODEL=openai/gpt-oss-120b
```

---

## GPU / Local Inference

For high-throughput state-wide runs, the pipeline can connect to a locally-hosted model on a rented GPU. This eliminates all rate limits and allows much higher concurrency.

**Recommended setup:**
1. Rent a GPU instance (e.g. Vast.ai, RunPod, Lambda Labs) with enough VRAM for the model (e.g. A100 80GB for `openai/gpt-oss-120b` at ~62GB)
2. Load the model using [vLLM](https://github.com/vllm-project/vllm) — it exposes an OpenAI-compatible API on port 18000
3. Set `LLM_PROVIDER=local` and point `LOCAL_LLM_BASE_URL` at the server

**Recommended `.env` for GPU runs:**

```env
LLM_PROVIDER=local
LOCAL_LLM_BASE_URL=http://127.0.0.1:18000/v1
LOCAL_LLM_MODEL=openai/gpt-oss-120b
MAX_CONCURRENT_LEADS=20
CRAWL_MAX_PAGES=10
CRAWL_DELAY_SECONDS=0.5
```

With a local model, the LLM is no longer the bottleneck — throughput is limited by the web crawler and the Maps API instead.

---

## Playwright Fallback

Some business websites are built with JavaScript frameworks (React, Vue, etc.) and render no meaningful content when fetched with a plain HTTP client. The Playwright fallback detects these pages and retries them with a headless Chromium browser.

**How it works:**
1. httpx fetches the page (fast, always runs)
2. If the extracted text is less than `CRAWL_PLAYWRIGHT_THRESHOLD` characters, Playwright opens a real browser tab, waits for JavaScript to finish, and grabs the fully-rendered HTML
3. The richer HTML is then passed to the LLM as normal

**Setup (one-time):**

```bash
playwright install chromium
```

**Enable in `.env`:**

```env
CRAWL_PLAYWRIGHT_FALLBACK=true
CRAWL_PLAYWRIGHT_THRESHOLD=800   # chars — below this, retry with Playwright
```

When `CRAWL_PLAYWRIGHT_FALLBACK=false` (the default), Playwright is never imported and does not need to be installed.

---

## Running Tests

```bash
python -m pytest tests/ -v
```

All tests are fully isolated — no API keys or network access required.

---

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `RAPIDAPI_KEY` | *(required)* | RapidAPI key for Maps Data API |
| `GROQ_API_KEY` | *(required)* | Groq API key |
| `LLM_PROVIDER` | `groq` | LLM backend: `groq`, `cerebras`, or `local` |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Groq model ID |
| `CEREBRAS_API_KEY` | | Cerebras API key (if using Cerebras) |
| `CEREBRAS_MODEL` | `llama-3.3-70b` | Cerebras model ID |
| `LOCAL_LLM_BASE_URL` | `http://localhost:8000/v1` | Base URL for local vLLM server |
| `LOCAL_LLM_MODEL` | `openai/gpt-oss-120b` | Model ID served by local vLLM |
| `MAX_CONCURRENT_LEADS` | `10` | Leads processed in parallel |
| `CRAWL_MAX_DEPTH` | `2` | How deep to follow internal links |
| `CRAWL_MAX_PAGES` | `10` | Max pages crawled per domain |
| `CRAWL_DELAY_SECONDS` | `1.0` | Polite delay between page fetches |
| `REQUEST_TIMEOUT_SECONDS` | `25` | HTTP timeout for all requests |
| `CRAWL_PLAYWRIGHT_FALLBACK` | `false` | Enable headless browser fallback for JS-rendered sites |
| `CRAWL_PLAYWRIGHT_THRESHOLD` | `800` | Min chars from httpx before triggering Playwright retry |
| `ZIP_MIN_POPULATION` | `1000` | Default min population filter for `--state` |

---

## Logs

Logs are written to `logs/run_YYYYMMDD.log` and also printed to the terminal. Each line follows ISO 8601 UTC format:

```
2026-05-11T12:52:14.638Z [INFO ] src.pipeline.lead_pipeline — Crawling https://example.com
2026-05-11T12:52:15.201Z [ERROR] src.scrapers.web_crawler — Timeout fetching https://example.com
```

Log levels: `DEBUG` (file only), `INFO`, `WARNING`, `ERROR`.
