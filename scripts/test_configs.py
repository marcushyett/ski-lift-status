#!/usr/bin/env python3
"""
Test runner for ski resort status configurations.

This script tests the scraping adapters against live resort API endpoints
using simple HTTP requests only - NO browser automation.

The configs store direct API endpoints that can be fetched with httpx.
This allows testing to run cheaply and quickly on any platform.

Usage:
    # Test all resorts
    python scripts/test_configs.py

    # Test a specific resort by ID
    python scripts/test_configs.py --resort-id 68b126bc3175516c9263aed7635d14e37ff360dc

    # Output JSON results
    python scripts/test_configs.py --output results.json
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ski_lift_status.scraping.resort_config import (
    ResortConfig,
    get_all_resort_configs,
    get_resort_config,
)
from ski_lift_status.scraping.adapters import lumiplan, skiplan
from ski_lift_status.data_fetcher import load_lifts, load_runs


@dataclass
class LiftResult:
    """Result for a single lift."""
    name: str
    status: str | None
    lift_type: str | None = None


@dataclass
class TrailResult:
    """Result for a single trail/run."""
    name: str
    status: str | None
    difficulty: str | None = None
    grooming: str | None = None


@dataclass
class ResortTestResult:
    """Test result for a single resort."""
    resort_id: str
    resort_name: str
    status_page_url: str  # First API endpoint for reference
    success: bool
    platform: str | None = None
    extraction_method: str | None = None

    # Counts
    total_lifts: int = 0
    open_lifts: int = 0
    closed_lifts: int = 0

    total_trails: int = 0
    open_trails: int = 0
    closed_trails: int = 0

    # Coverage against OpenSkiMap
    openskimap_lift_count: int = 0
    openskimap_trail_count: int = 0
    lift_coverage: float = 0.0
    trail_coverage: float = 0.0

    # Sample data
    sample_lifts: list[LiftResult] = field(default_factory=list)
    sample_trails: list[TrailResult] = field(default_factory=list)

    # Timing
    fetch_time_ms: float = 0.0

    # Errors
    error: str | None = None


@dataclass
class TestSummary:
    """Summary of all test results."""
    timestamp: str
    total_resorts: int = 0
    passing_resorts: int = 0
    failing_resorts: int = 0
    results: list[ResortTestResult] = field(default_factory=list)


def get_extraction_method_description(platform: str) -> str:
    """Get a human-readable description of the extraction method."""
    descriptions = {
        "lumiplan": (
            "Lumiplan REST API (HTTP-only) - Fetches JSON from staticPoiData and "
            "dynamicPoiData endpoints. Extracts name, type, and operational status "
            "directly from JSON responses using simple field mapping."
        ),
        "skiplan": (
            "Skiplan HTTP API (HTTP-only) - Fetches HTML from getOuvertures.php "
            "endpoint. Parses .ouvertures-marker elements using BeautifulSoup to extract "
            "name, status, and type information from HTML structure."
        ),
    }
    return descriptions.get(platform, f"Unknown platform: {platform}")


def calculate_coverage(
    extracted_names: list[str],
    reference_names: list[str],
) -> float:
    """Calculate coverage of extracted names against reference data."""
    if not reference_names:
        return 0.0

    def normalize(name: str) -> str:
        return name.lower().strip()

    extracted_normalized = {normalize(n) for n in extracted_names}
    reference_normalized = {normalize(n) for n in reference_names}

    # Check how many reference names are found in extracted
    matched = 0
    for ref_name in reference_normalized:
        for ext_name in extracted_normalized:
            # Check for substring match in either direction
            if ref_name in ext_name or ext_name in ref_name:
                matched += 1
                break

    return matched / len(reference_normalized) if reference_normalized else 0.0


async def test_resort(
    config: ResortConfig,
    reference_lifts: list,
    reference_runs: list,
) -> ResortTestResult:
    """Test a single resort's status using HTTP-only fetching."""
    result = ResortTestResult(
        resort_id=config.resort_id,
        resort_name=config.resort_name,
        status_page_url=config.api_endpoints[0] if config.api_endpoints else "",
        success=False,
        platform=config.platform,
    )

    # Get reference data for this resort
    resort_lift_names = [
        lift.name for lift in reference_lifts
        if config.resort_id in (lift.ski_area_ids or "").split(";")
    ]
    resort_run_names = [
        run.name for run in reference_runs
        if config.resort_id in (run.ski_area_ids or "").split(";")
    ]

    result.openskimap_lift_count = len(resort_lift_names)
    result.openskimap_trail_count = len(resort_run_names)
    result.extraction_method = get_extraction_method_description(config.platform)

    start_time = time.time()

    try:
        # Fetch data using platform-specific HTTP-only functions
        data = None

        if config.platform == "lumiplan":
            map_uuid = config.platform_config.get("map_uuid")
            if not map_uuid:
                result.error = "Missing map_uuid in platform_config"
                return result
            data = await lumiplan.fetch_live_status(map_uuid)

        elif config.platform == "skiplan":
            resort_slug = config.platform_config.get("resort_slug")
            if not resort_slug:
                result.error = "Missing resort_slug in platform_config"
                return result
            data = await skiplan.fetch_live_status(resort_slug)

        else:
            result.error = f"Unknown platform: {config.platform}"
            return result

        result.fetch_time_ms = (time.time() - start_time) * 1000

        if not data:
            result.error = f"Fetch returned no data for platform {config.platform}"
            return result

        # Process lifts
        if hasattr(data, 'lifts'):
            extracted_lift_names = []
            for lift in data.lifts:
                extracted_lift_names.append(lift.name)

                # Count by status
                status = getattr(lift, 'status', None) or getattr(lift, 'opening_status', None)
                if status:
                    status_lower = status.lower()
                    if 'open' in status_lower:
                        result.open_lifts += 1
                    elif 'close' in status_lower:
                        result.closed_lifts += 1

                # Add to samples (first 3)
                if len(result.sample_lifts) < 3:
                    result.sample_lifts.append(LiftResult(
                        name=lift.name,
                        status=status,
                        lift_type=getattr(lift, 'lift_type', None),
                    ))

            result.total_lifts = len(data.lifts)
            result.lift_coverage = calculate_coverage(extracted_lift_names, resort_lift_names)

        # Process trails
        if hasattr(data, 'trails'):
            extracted_trail_names = []
            for trail in data.trails:
                extracted_trail_names.append(trail.name)

                # Count by status
                status = getattr(trail, 'status', None) or getattr(trail, 'opening_status', None)
                if status:
                    status_lower = status.lower()
                    if 'open' in status_lower:
                        result.open_trails += 1
                    elif 'close' in status_lower:
                        result.closed_trails += 1

                # Add to samples (first 3)
                if len(result.sample_trails) < 3:
                    result.sample_trails.append(TrailResult(
                        name=trail.name,
                        status=status,
                        difficulty=getattr(trail, 'difficulty', None),
                        grooming=getattr(trail, 'grooming_status', None),
                    ))

            result.total_trails = len(data.trails)
            result.trail_coverage = calculate_coverage(extracted_trail_names, resort_run_names)

        # Mark as success if we got any data
        result.success = result.total_lifts > 0 or result.total_trails > 0

    except Exception as e:
        result.fetch_time_ms = (time.time() - start_time) * 1000
        result.error = str(e)

    return result


def print_result(result: ResortTestResult) -> None:
    """Print a single resort's test result."""
    status_icon = "+" if result.success else "x"
    print(f"\n{'='*70}")
    print(f"[{status_icon}] {result.resort_name}")
    print(f"{'='*70}")
    print(f"Resort ID: {result.resort_id}")
    print(f"API Endpoint: {result.status_page_url}")
    print(f"Fetch time: {result.fetch_time_ms:.0f}ms")

    if result.error:
        print(f"\n[x] Error: {result.error}")
        return

    print(f"\nPlatform: {result.platform}")
    print("\nExtraction Method:")
    print(f"   {result.extraction_method}")

    # Lift summary
    print(f"\nLifts: {result.total_lifts} total")
    print(f"   Open: {result.open_lifts} | Closed: {result.closed_lifts}")
    print(f"   Coverage vs OpenSkiMap: {result.lift_coverage:.1%} ({result.openskimap_lift_count} reference lifts)")

    if result.sample_lifts:
        print("\n   Sample lifts:")
        for lift in result.sample_lifts:
            type_str = f" ({lift.lift_type})" if lift.lift_type else ""
            print(f"   - {lift.name}{type_str}: {lift.status or 'unknown'}")

    # Trail summary
    print(f"\nTrails: {result.total_trails} total")
    print(f"   Open: {result.open_trails} | Closed: {result.closed_trails}")
    print(f"   Coverage vs OpenSkiMap: {result.trail_coverage:.1%} ({result.openskimap_trail_count} reference trails)")

    if result.sample_trails:
        print("\n   Sample trails:")
        for trail in result.sample_trails:
            diff_str = f" [{trail.difficulty}]" if trail.difficulty else ""
            print(f"   - {trail.name}{diff_str}: {trail.status or 'unknown'}")


def print_summary(summary: TestSummary) -> None:
    """Print the test summary."""
    print(f"\n{'='*70}")
    print("TEST SUMMARY")
    print(f"{'='*70}")
    print(f"Timestamp: {summary.timestamp}")
    print(f"Total resorts tested: {summary.total_resorts}")
    print(f"[+] Passing: {summary.passing_resorts}")
    print(f"[x] Failing: {summary.failing_resorts}")

    if summary.passing_resorts > 0:
        passing = [r for r in summary.results if r.success]
        avg_lifts = sum(r.total_lifts for r in passing) / len(passing)
        avg_trails = sum(r.total_trails for r in passing) / len(passing)
        avg_lift_coverage = sum(r.lift_coverage for r in passing) / len(passing)
        avg_trail_coverage = sum(r.trail_coverage for r in passing) / len(passing)

        print("\nAverages (passing resorts):")
        print(f"  Lifts per resort: {avg_lifts:.0f}")
        print(f"  Trails per resort: {avg_trails:.0f}")
        print(f"  Lift coverage: {avg_lift_coverage:.1%}")
        print(f"  Trail coverage: {avg_trail_coverage:.1%}")


def generate_badge_json(summary: TestSummary) -> dict:
    """Generate JSON for shields.io badge."""
    if summary.failing_resorts == 0:
        color = "brightgreen"
        message = f"{summary.passing_resorts} passing"
    elif summary.passing_resorts == 0:
        color = "red"
        message = f"{summary.failing_resorts} failing"
    else:
        color = "yellow"
        message = f"{summary.passing_resorts}/{summary.total_resorts} passing"

    return {
        "schemaVersion": 1,
        "label": "resort configs",
        "message": message,
        "color": color,
    }


async def main():
    parser = argparse.ArgumentParser(description="Test ski resort status configurations (HTTP-only)")
    parser.add_argument(
        "--resort-id",
        help="Test only a specific resort by ID",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output JSON results to file",
    )
    parser.add_argument(
        "--badge-output",
        help="Output badge JSON to file",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only output summary (no per-resort details)",
    )
    args = parser.parse_args()

    # Load resort configs
    if args.resort_id:
        config = get_resort_config(args.resort_id)
        if not config:
            print(f"[x] Resort ID not found in configs: {args.resort_id}")
            print("\nAvailable resort IDs:")
            for c in get_all_resort_configs():
                print(f"  - {c.resort_id} ({c.resort_name})")
            sys.exit(1)
        configs = [config]
    else:
        configs = get_all_resort_configs()

    if not configs:
        print("[x] No resort configs found")
        sys.exit(1)

    # Load reference data
    print("Loading OpenSkiMap reference data...")
    reference_lifts = load_lifts()
    reference_runs = load_runs()
    print(f"  Loaded {len(reference_lifts)} lifts and {len(reference_runs)} runs")

    # Test each resort
    print(f"\nTesting {len(configs)} resort(s) using HTTP-only fetching...\n")

    summary = TestSummary(
        timestamp=datetime.utcnow().isoformat() + "Z",
        total_resorts=len(configs),
    )

    for config in configs:
        if not args.quiet:
            print(f"Testing {config.resort_name} ({config.platform})...")

        result = await test_resort(config, reference_lifts, reference_runs)
        summary.results.append(result)

        if result.success:
            summary.passing_resorts += 1
        else:
            summary.failing_resorts += 1

        if not args.quiet:
            print_result(result)

    # Print summary
    print_summary(summary)

    # Output JSON if requested
    if args.output:
        output_data = {
            "timestamp": summary.timestamp,
            "total_resorts": summary.total_resorts,
            "passing_resorts": summary.passing_resorts,
            "failing_resorts": summary.failing_resorts,
            "results": [
                {
                    "resort_id": r.resort_id,
                    "resort_name": r.resort_name,
                    "status_page_url": r.status_page_url,
                    "success": r.success,
                    "platform": r.platform,
                    "extraction_method": r.extraction_method,
                    "total_lifts": r.total_lifts,
                    "open_lifts": r.open_lifts,
                    "closed_lifts": r.closed_lifts,
                    "total_trails": r.total_trails,
                    "open_trails": r.open_trails,
                    "closed_trails": r.closed_trails,
                    "lift_coverage": r.lift_coverage,
                    "trail_coverage": r.trail_coverage,
                    "openskimap_lift_count": r.openskimap_lift_count,
                    "openskimap_trail_count": r.openskimap_trail_count,
                    "sample_lifts": [
                        {"name": lift.name, "status": lift.status, "lift_type": lift.lift_type}
                        for lift in r.sample_lifts
                    ],
                    "sample_trails": [
                        {"name": t.name, "status": t.status, "difficulty": t.difficulty}
                        for t in r.sample_trails
                    ],
                    "fetch_time_ms": r.fetch_time_ms,
                    "error": r.error,
                }
                for r in summary.results
            ],
        }

        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\nResults saved to: {args.output}")

    # Output badge JSON if requested
    if args.badge_output:
        badge_data = generate_badge_json(summary)
        with open(args.badge_output, "w") as f:
            json.dump(badge_data, f, indent=2)
        print(f"Badge JSON saved to: {args.badge_output}")

    # Exit with error code if any failures
    sys.exit(0 if summary.failing_resorts == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
