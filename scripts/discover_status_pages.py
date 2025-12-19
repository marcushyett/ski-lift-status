#!/usr/bin/env python3
"""Script to discover lift status pages for ski resorts."""

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

import structlog

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ski_lift_status import load_resorts, load_lifts, get_lifts_for_resort
from ski_lift_status.scraping.discovery import DiscoveryAgent, DiscoveryResult

logger = structlog.get_logger()

DATA_DIR = Path(__file__).parent.parent / "data"
STATUS_PAGES_FILE = DATA_DIR / "status_pages.csv"


def load_existing_status_pages() -> dict[str, dict]:
    """Load existing status pages CSV."""
    existing = {}
    if STATUS_PAGES_FILE.exists():
        with open(STATUS_PAGES_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing[row["resort_id"]] = row
    return existing


def save_status_pages(entries: list[dict]) -> None:
    """Save status pages to CSV."""
    fieldnames = ["resort_id", "resort_name", "website_url", "status_page_url"]

    with open(STATUS_PAGES_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry)


def get_top_resorts_by_lifts(resorts, lifts, top_n: int = 30) -> list:
    """Get top N resorts by number of lifts.

    Args:
        resorts: List of Resort objects.
        lifts: List of all Lift objects.
        top_n: Number of top resorts to return.

    Returns:
        List of (resort, lift_count) tuples sorted by lift count.
    """
    resort_lift_counts = {}

    for lift in lifts:
        if not lift.ski_area_ids:
            continue
        for ski_area_id in lift.ski_area_ids.split(";"):
            ski_area_id = ski_area_id.strip()
            if ski_area_id:
                resort_lift_counts[ski_area_id] = resort_lift_counts.get(ski_area_id, 0) + 1

    # Create resort lookup
    resort_by_id = {r.id: r for r in resorts}

    # Sort by lift count
    sorted_resorts = sorted(
        [(resort_by_id.get(rid), count) for rid, count in resort_lift_counts.items()
         if resort_by_id.get(rid)],
        key=lambda x: x[1],
        reverse=True,
    )

    return sorted_resorts[:top_n]


async def discover_status_page(
    resort_id: str,
    resort_name: str,
    resort_website: str | None,
    lifts: list,
) -> DiscoveryResult:
    """Discover status page for a single resort."""
    agent = DiscoveryAgent()

    lift_names = [lift.name for lift in lifts if lift.name]

    return await agent.discover(
        resort_id=resort_id,
        resort_name=resort_name,
        lift_names=lift_names,
        resort_website=resort_website,
    )


async def run_discovery(
    resort_ids: list[str] | None = None,
    top_n: int | None = None,
    override: bool = False,
    output_json: str | None = None,
) -> list[DiscoveryResult]:
    """Run discovery for resorts.

    Args:
        resort_ids: Specific resort IDs to discover. If None, uses top_n.
        top_n: Number of top resorts by lifts to discover.
        override: If True, re-discover even if already in CSV.
        output_json: Path to write JSON results.

    Returns:
        List of DiscoveryResult objects.
    """
    resorts = load_resorts()
    all_lifts = load_lifts()
    existing = load_existing_status_pages()

    resort_by_id = {r.id: r for r in resorts}

    # Determine which resorts to process
    resorts_to_process = []

    if resort_ids:
        # Specific resorts requested
        for rid in resort_ids:
            if rid in resort_by_id:
                resort = resort_by_id[rid]
                if not override and rid in existing:
                    logger.info("skipping_existing", resort_id=rid, resort_name=resort.name)
                    continue
                resorts_to_process.append(resort)
            else:
                logger.warning("resort_not_found", resort_id=rid)
    else:
        # Use top N resorts
        n = top_n or 30
        top_resorts = get_top_resorts_by_lifts(resorts, all_lifts, n)

        for resort, lift_count in top_resorts:
            if not override and resort.id in existing:
                logger.info("skipping_existing", resort_id=resort.id, resort_name=resort.name)
                continue
            resorts_to_process.append(resort)

    logger.info("resorts_to_process", count=len(resorts_to_process))

    # Run discovery
    results = []
    for resort in resorts_to_process:
        lifts = get_lifts_for_resort(resort.id)
        website = resort.websites.split(";")[0].strip() if resort.websites else None

        logger.info(
            "discovering",
            resort_id=resort.id,
            resort_name=resort.name,
            lift_count=len(lifts),
        )

        try:
            result = await discover_status_page(
                resort_id=resort.id,
                resort_name=resort.name,
                resort_website=website,
                lifts=lifts,
            )
            results.append(result)

            if result.success:
                logger.info(
                    "discovered",
                    resort_name=resort.name,
                    url=result.status_page_url,
                    confidence=result.confidence,
                )
            else:
                logger.warning(
                    "discovery_failed",
                    resort_name=resort.name,
                    errors=result.errors,
                )

        except Exception as e:
            logger.error("discovery_error", resort_name=resort.name, error=str(e))
            results.append(DiscoveryResult(
                resort_id=resort.id,
                resort_name=resort.name,
                success=False,
                errors=[str(e)],
            ))

        # Rate limiting
        await asyncio.sleep(1.0)

    # Update status_pages.csv with new entries
    all_entries = []

    # Keep existing entries
    for rid, row in existing.items():
        # Skip if we're overriding this resort
        if override and any(r.resort_id == rid for r in results):
            continue
        all_entries.append(row)

    # Add new successful discoveries
    for result in results:
        if result.success and result.status_page_url:
            all_entries.append({
                "resort_id": result.resort_id,
                "resort_name": result.resort_name,
                "website_url": result.website_url or "",
                "status_page_url": result.status_page_url,
            })

    # Sort by resort name
    all_entries.sort(key=lambda x: x["resort_name"])

    # Save updated CSV
    save_status_pages(all_entries)
    logger.info("saved_status_pages", count=len(all_entries))

    # Output JSON if requested
    if output_json:
        json_results = []
        for r in results:
            json_results.append({
                "resort_id": r.resort_id,
                "resort_name": r.resort_name,
                "success": r.success,
                "status_page_url": r.status_page_url,
                "website_url": r.website_url,
                "confidence": r.confidence,
                "reasoning": r.reasoning,
                "search_queries": r.search_queries,
                "candidate_urls": r.candidate_urls,
                "errors": r.errors,
            })

        with open(output_json, "w") as f:
            json.dump({
                "results": json_results,
                "total": len(results),
                "successful": sum(1 for r in results if r.success),
                "failed": sum(1 for r in results if not r.success),
            }, f, indent=2)

        logger.info("saved_json_results", path=output_json)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Discover lift status pages for ski resorts"
    )
    parser.add_argument(
        "--resort-id",
        type=str,
        help="Specific resort ID to discover",
    )
    parser.add_argument(
        "--resort-ids",
        type=str,
        help="Comma-separated list of resort IDs",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=30,
        help="Number of top resorts by lift count (default: 30)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Discover for all resorts",
    )
    parser.add_argument(
        "--override",
        action="store_true",
        help="Override existing entries in status_pages.csv",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Path to write JSON results",
    )

    args = parser.parse_args()

    # Configure logging
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )

    # Determine resort IDs
    resort_ids = None
    if args.resort_id:
        resort_ids = [args.resort_id]
    elif args.resort_ids:
        resort_ids = [rid.strip() for rid in args.resort_ids.split(",")]
    elif args.all:
        # Load all resorts
        resorts = load_resorts()
        resort_ids = [r.id for r in resorts]

    # Run discovery
    results = asyncio.run(run_discovery(
        resort_ids=resort_ids,
        top_n=args.top if not resort_ids else None,
        override=args.override,
        output_json=args.output,
    ))

    # Print summary
    successful = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    print(f"\n{'='*60}")
    print(f"Discovery Complete")
    print(f"{'='*60}")
    print(f"Total processed: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")

    if successful > 0:
        print(f"\nDiscovered status pages:")
        for r in results:
            if r.success:
                print(f"  - {r.resort_name}: {r.status_page_url}")
                print(f"    Confidence: {r.confidence:.1%}")


if __name__ == "__main__":
    import logging
    main()
