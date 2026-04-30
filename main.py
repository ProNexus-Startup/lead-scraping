"""
Entry point for the Pronexus lead scraping pipeline.

Usage examples:
  python main.py --query "plumbers in Austin TX" --limit 20
  python main.py --query "dentists in Chicago IL" --limit 50
  python main.py --query "HVAC companies" --regions Texas Florida Ohio --limit 50
  python main.py --query "plumbers" --regions "New York" California --limit 100 --label plumbers_q2
"""

import argparse
import asyncio
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Google Maps leads, crawl their websites, and extract owner contact info."
    )
    parser.add_argument("--query", required=True, help='Search query, e.g. "plumbers" or "plumbers in Austin TX"')
    parser.add_argument("--limit", type=int, default=1, help="Max leads per region (or total if no --regions). Default: 1")
    parser.add_argument("--label", default="", help="Optional label appended to the output CSV filename")
    parser.add_argument(
        "--regions",
        nargs="+",
        metavar="REGION",
        default=[],
        help='One or more states or countries to search. Appended to --query automatically. '
             'E.g. --regions Ohio Texas Florida  or  --regions "New York" California',
    )
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

    regions = args.regions or [""]  # single empty string = run the query as-is
    total_requests = args.limit * len([r for r in regions if r])  # only count non-empty regions
    effective_requests = args.limit * len(regions)

    if effective_requests > 100:
        print(
            f"[WARNING] This run will make up to {effective_requests} Maps API requests "
            f"({args.limit} per region × {len(regions)} region(s))."
        )
        confirm = input("Type 'yes' to continue: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            sys.exit(0)

    output_paths = []
    for region in regions:
        query = f"{args.query} in {region}" if region else args.query
        label = _build_label(args.label, region)

        csv_path = asyncio.run(run(query=query, limit=args.limit, output_label=label))

        if csv_path:
            print(f"\nDone. Output saved to: {csv_path}")
            output_paths.append(csv_path)
        else:
            print(f"\n[WARNING] Pipeline produced no output for region '{region or 'default'}'. Check logs/.")

    if not output_paths:
        print("\nNo output produced for any region. Check logs/ for details.")
        sys.exit(1)


def _build_label(base_label: str, region: str) -> str:
    """Combine an optional base label with a region name for the output filename."""
    region_slug = region.lower().replace(" ", "_") if region else ""
    if base_label and region_slug:
        return f"{base_label}_{region_slug}"
    return base_label or region_slug


if __name__ == "__main__":
    main()
