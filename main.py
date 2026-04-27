"""
Entry point for the Pronexus lead scraping pipeline.

Usage examples:
  python main.py --query "plumbers in Austin TX" --limit 1
  python main.py --query "dentists in Chicago IL" --limit 50
  python main.py --query "HVAC companies in Dallas TX" --limit 100 --label hvac_dallas
"""

import argparse
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Google Maps leads, crawl their websites, and extract owner contact info."
    )
    parser.add_argument("--query", required=True, help='Search query, e.g. "plumbers in Austin TX"')
    parser.add_argument("--limit", type=int, default=1, help="Max number of businesses to scrape (default: 1)")
    parser.add_argument("--label", default="", help="Optional label appended to the output CSV filename")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Import after arg parsing so --help works even without a .env file
    try:
        from src.pipeline.lead_pipeline import run
    except KeyError as exc:
        print(f"[ERROR] Missing environment variable: {exc}")
        print("        Copy .env.example to .env and fill in your API keys.")
        sys.exit(1)

    if args.limit > 100:
        print(f"[WARNING] --limit {args.limit} will use {args.limit} of your 1,000 monthly RapidAPI requests.")
        confirm = input("Type 'yes' to continue: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            sys.exit(0)

    csv_path = run(query=args.query, limit=args.limit, output_label=args.label)

    if csv_path:
        print(f"\nDone. Output saved to: {csv_path}")
    else:
        print("\nPipeline produced no output. Check logs/ for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
