"""
Entry point for the Pronexus lead scraping pipeline.

Usage examples:
  python main.py --query "dentists" --state TX --limit 5
  python main.py --query "pizza restaurant" --state CA --min-pop 5000 --limit 3
  python main.py --query "gym" --zips 90210,90401,91101 --limit 5
  python main.py --query "plumbers in Austin TX" --limit 20
"""

import argparse
import asyncio
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Google Maps leads, crawl their websites, and extract owner contact info."
    )
    parser.add_argument("--query", "-q", required=True, help='Search query, e.g. "plumbers" or "dentists"')
    parser.add_argument(
        "--limit", type=int, default=1,
        help="Max leads per ZIP (ZIP mode) or total leads (direct mode). Default: 1",
    )
    parser.add_argument("--label", default="", help="Optional label appended to the output CSV filename")
    parser.add_argument(
        "--state", "-s", default="",
        help="2-letter US state code. Searches all ZIPs in that state. E.g. --state TX",
    )
    parser.add_argument(
        "--zips", "-z", default="",
        help="Comma-separated ZIP codes to search. E.g. --zips 90210,90401,91101",
    )
    parser.add_argument(
        "--min-pop", type=int, default=1000,
        help="Minimum ZIP population filter (use with --state). Default: 1000",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume a previous ZIP run from where it left off.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Import after arg parsing so --help works even without a .env file
    try:
        from src.pipeline.lead_pipeline import run, run_zips
    except KeyError as exc:
        print(f"[ERROR] Missing environment variable: {exc}")
        print("        Copy .env.example to .env and fill in your API keys.")
        sys.exit(1)

    # --- ZIP mode ---
    if args.state or args.zips:
        from src.scrapers.zip_loader import load_zips_for_state, parse_zip_list

        if args.state and args.zips:
            print("[ERROR] Use --state OR --zips, not both.")
            sys.exit(1)

        if args.state:
            zip_codes = load_zips_for_state(args.state, min_population=args.min_pop)
            if not zip_codes:
                print(f"[ERROR] No ZIP codes found for --state {args.state!r} with --min-pop {args.min_pop}.")
                sys.exit(1)
            print(f"Found {len(zip_codes)} ZIP codes in {args.state.upper()} with population >= {args.min_pop}")
        else:
            zip_codes = parse_zip_list(args.zips)
            if not zip_codes:
                print("[ERROR] --zips produced an empty list. Check the format: --zips 90210,90401")
                sys.exit(1)

        total_requests = len(zip_codes) * args.limit
        if total_requests > 100:
            print(
                f"[WARNING] This run will make up to {total_requests} Maps API requests "
                f"({args.limit} per ZIP × {len(zip_codes)} ZIPs)."
            )
            confirm = input("Type 'yes' to continue: ").strip().lower()
            if confirm != "yes":
                print("Aborted.")
                sys.exit(0)

        label = args.label or (args.state.lower() if args.state else "zips")
        csv_path = asyncio.run(
            run_zips(
                query=args.query,
                zip_codes=zip_codes,
                limit_per_zip=args.limit,
                output_label=label,
                resume=args.resume,
            )
        )

        if csv_path:
            print(f"\nDone. Output saved to: {csv_path}")
        else:
            print("\n[WARNING] Pipeline produced no output. Check logs/.")
            sys.exit(1)
        return

    # --- Direct query mode ---
    if args.limit > 100:
        print(f"[WARNING] This run will make up to {args.limit} Maps API requests.")
        confirm = input("Type 'yes' to continue: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            sys.exit(0)

    csv_path = asyncio.run(run(query=args.query, limit=args.limit, output_label=args.label))

    if csv_path:
        print(f"\nDone. Output saved to: {csv_path}")
    else:
        print("\nNo output produced. Check logs/ for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
