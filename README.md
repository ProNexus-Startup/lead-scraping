# Pronexus Lead Scraping Pipeline

An automated pipeline that collects business leads from Google Maps, crawls their websites, and uses an LLM to extract the most likely owner name and contact email — all exported to a clean CSV file.

---

## What It Does

1. **Maps Collection** — Queries Google Maps via RapidAPI for businesses by category and location (plumbers, HVAC, dentists, etc.) and captures name, phone, address, website, rating, and review count.
2. **Website Crawling** — For each business that has a website, crawls the homepage and up to depth 2 of same-domain internal links, prioritising `/about`, `/team`, and `/contact` pages.
3. **Owner Extraction** — Sends the collected page text to a Groq-hosted LLM, which identifies the most likely owner or founder and their best contact email.
4. **CSV Export** — Writes all results to a timestamped CSV file in the `output/` directory.

---

## Project Structure

```
lead-scraping/
├── config/
│   └── settings.py           # All configuration loaded from .env
├── src/
│   ├── models/lead.py        # Lead data model and CSV serialisation
│   ├── scrapers/
│   │   ├── maps_scraper.py   # RapidAPI Google Maps integration
│   │   └── web_crawler.py    # Same-domain website crawler
│   ├── extractors/
│   │   └── llm_extractor.py  # Groq LLM prompt and response parsing
│   ├── pipeline/
│   │   └── lead_pipeline.py  # Orchestrates the full scrape → crawl → extract flow
│   └── utils/
│       ├── logger.py         # Console + daily log file output
│       └── csv_writer.py     # Timestamped CSV writer
├── tests/                    # Unit tests (no network calls required)
├── output/                   # Generated CSV files (git-ignored)
├── logs/                     # Daily run logs (git-ignored)
├── .env.example              # Environment variable template
├── requirements.txt
└── main.py                   # CLI entry point
```

---

## Setup

**Prerequisites:** Python 3.11+, a RapidAPI account with the [Maps Data by Alexandar Vikhorev](https://rapidapi.com/alexanderxbx/api/maps-data) subscription, and a Groq API key.

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

```
RAPIDAPI_KEY=your_rapidapi_key_here
GROQ_API_KEY=your_groq_api_key_here
```

---

## Usage

**Test with a single lead (recommended first run)**

```bash
python main.py --query "plumbers in Austin TX" --limit 1
```

**Scrape a full batch**

```bash
python main.py --query "dentists in Chicago IL" --limit 50 --label dentists_chicago
```

**Available options**

| Flag | Default | Description |
|------|---------|-------------|
| `--query` | *(required)* | Search query passed to Google Maps |
| `--limit` | `1` | Maximum number of businesses to process |
| `--label` | *(empty)* | Optional suffix added to the output CSV filename |

**Output CSV columns**

| Column | Description |
|--------|-------------|
| `business_name` | Business name from Google Maps |
| `category` | Business category (e.g. Plumber, Dentist) |
| `phone` | Phone number |
| `address` | Full address |
| `website` | Business website URL |
| `rating` | Google Maps star rating |
| `reviews_count` | Number of reviews |
| `owner_name` | LLM-identified owner or founder name |
| `owner_email` | Best contact email found on the website |
| `llm_confidence` | `high`, `medium`, or `low` |
| `scraped_at` | UTC timestamp of the run |
| `status` | `success`, `no_website`, `crawl_failed`, or `llm_failed` |

---

## Running Tests

```bash
python -m pytest tests/ -v
```

Tests are fully isolated — no API keys or network access required.

---

## Rate Limits and Scaling

| Service | Free Tier Limit | Notes |
|---------|----------------|-------|
| RapidAPI Maps | ~1,000 requests / month | Each `--limit N` run uses N requests |
| Groq API | Generous free tier | One LLM call per business with a website |
| Web crawling | No limit | 1-second delay between page fetches by default |

Start with `--limit 1` to verify your setup, then gradually increase. Logs in `logs/` provide a full record of every run.

---

## Configuration Reference

All settings can be overridden in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Groq model ID |
| `CRAWL_MAX_DEPTH` | `2` | How deep to follow internal links |
| `CRAWL_MAX_PAGES` | `10` | Max pages crawled per domain |
| `CRAWL_DELAY_SECONDS` | `1.0` | Polite delay between page requests |
| `REQUEST_TIMEOUT_SECONDS` | `15` | HTTP timeout for all requests |
