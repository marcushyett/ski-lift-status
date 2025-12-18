#!/usr/bin/env python3
"""Script to run the scraping pipeline for ski resort status pages."""

import argparse
import asyncio
import sys
from pathlib import Path

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ski_lift_status.scraping import (
    load_status_pages,
    run_pipeline_for_resort,
    run_pipeline_for_all,
)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run the scraping pipeline for ski resort status pages."
    )
    parser.add_argument(
        "--resort-id",
        type=str,
        help="Run pipeline for a specific resort ID",
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Status page URL (required with --resort-id)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run pipeline for all configured resorts",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default: True)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser with visible UI",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use mock LLM (no API calls)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum refinement attempts (default: 3)",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=0.20,
        help="Minimum coverage threshold (default: 0.20 = 20%%)",
    )

    args = parser.parse_args()

    headless = not args.no_headless

    if args.resort_id:
        if not args.url:
            parser.error("--url is required when using --resort-id")

        result = await run_pipeline_for_resort(
            resort_id=args.resort_id,
            status_page_url=args.url,
            headless=headless,
            use_mock_llm=args.mock_llm,
        )

        if result.success:
            print(f"\nSuccess! Extracted {len(result.lifts_data)} lifts and {len(result.runs_data)} runs")
            print(f"Coverage: lifts={result.lift_coverage:.1%}, runs={result.run_coverage:.1%}")
        else:
            print(f"\nFailed. Errors: {result.errors}")
            sys.exit(1)

    elif args.all:
        results = await run_pipeline_for_all(
            headless=headless,
            use_mock_llm=args.mock_llm,
        )

        # Exit with error if any failed
        failed = [r for r in results.values() if not r.success]
        if failed:
            sys.exit(1)

    else:
        # List available resorts
        status_pages = load_status_pages()
        print("Available resorts:")
        for entry in status_pages:
            print(f"  {entry.resort_id}: {entry.resort_name}")
        print("\nUse --resort-id and --url to run for a specific resort")
        print("Use --all to run for all configured resorts")


if __name__ == "__main__":
    asyncio.run(main())
