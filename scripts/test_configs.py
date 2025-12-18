#!/usr/bin/env python3
"""
Test runner for ski resort status configurations.

This script tests the scraping adapters against live resort status pages,
reporting on lift/run status, coverage against OpenSkiMap data, and
extraction method details.

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
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ski_lift_status.scraping.page_loader import PageLoader
from ski_lift_status.scraping.adapters import detect_platform, extract_with_adapter
from ski_lift_status.scraping.pipeline import load_status_pages, StatusPageEntry
from ski_lift_status.data_fetcher import load_lifts, load_runs


@dataclass
class LiftResult:
    """Result for a single lift."""
    name: str
    status: str | None
    lift_type: str | None = None
    wait_time: str | None = None
    open_time: str | None = None
    close_time: str | None = None


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
    status_page_url: str
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
            "Lumiplan REST API - Extracts data from JSON endpoints "
            "(staticPoiData for lift/run metadata, dynamicPoiData for live status). "
            "Uses JSON path selectors to extract name, type, and operational status."
        ),
        "skiplan": (
            "Skiplan Server-Side Rendered HTML - Parses HTML from getOuvertures.php "
            "XHR response. Uses CSS selectors on .ouvertures-marker elements to extract "
            "name (from .marker-title), status (from .marker-content classes), and "
            "type (from icon SVG filenames like prl_tc_black.svg for télécabine)."
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

    # Normalize names for comparison
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
    entry: StatusPageEntry,
    reference_lifts: list,
    reference_runs: list,
) -> ResortTestResult:
    """Test a single resort's status page."""
    result = ResortTestResult(
        resort_id=entry.resort_id,
        resort_name=entry.resort_name,
        status_page_url=entry.status_page_url,
        success=False,
    )

    # Get reference data for this resort
    resort_lift_names = [
        lift.name for lift in reference_lifts
        if entry.resort_id in (lift.ski_area_ids or "").split(";")
    ]
    resort_run_names = [
        run.name for run in reference_runs
        if entry.resort_id in (run.ski_area_ids or "").split(";")
    ]

    result.openskimap_lift_count = len(resort_lift_names)
    result.openskimap_trail_count = len(resort_run_names)

    try:
        # Load page and capture resources
        loader = PageLoader(headless=True, timeout_ms=45000, wait_after_load_ms=5000)
        capture = await loader.load_page(entry.status_page_url, entry.resort_id)
        result.fetch_time_ms = capture.load_time_ms

        if capture.errors:
            result.error = "; ".join(capture.errors)
            return result

        # Detect platform
        platform = detect_platform(capture.resources)
        if not platform:
            result.error = "Could not detect platform from captured resources"
            return result

        result.platform = platform
        result.extraction_method = get_extraction_method_description(platform)

        # Extract data using adapter
        data = extract_with_adapter(platform, capture.resources)
        if not data:
            result.error = f"Extraction failed for platform {platform}"
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
        result.error = str(e)

    return result


def print_result(result: ResortTestResult) -> None:
    """Print a single resort's test result."""
    status_icon = "✅" if result.success else "❌"
    print(f"\n{'='*70}")
    print(f"{status_icon} {result.resort_name}")
    print(f"{'='*70}")
    print(f"Resort ID: {result.resort_id}")
    print(f"URL: {result.status_page_url}")
    print(f"Fetch time: {result.fetch_time_ms:.0f}ms")

    if result.error:
        print(f"\n❌ Error: {result.error}")
        return

    print(f"\n📊 Platform: {result.platform}")
    print("\n📝 Extraction Method:")
    print(f"   {result.extraction_method}")

    # Lift summary
    print(f"\n🚡 Lifts: {result.total_lifts} total")
    print(f"   Open: {result.open_lifts} | Closed: {result.closed_lifts}")
    print(f"   Coverage vs OpenSkiMap: {result.lift_coverage:.1%} ({result.openskimap_lift_count} reference lifts)")

    if result.sample_lifts:
        print("\n   Sample lifts:")
        for lift in result.sample_lifts:
            type_str = f" ({lift.lift_type})" if lift.lift_type else ""
            print(f"   • {lift.name}{type_str}: {lift.status or 'unknown'}")

    # Trail summary
    print(f"\n⛷️  Trails: {result.total_trails} total")
    print(f"   Open: {result.open_trails} | Closed: {result.closed_trails}")
    print(f"   Coverage vs OpenSkiMap: {result.trail_coverage:.1%} ({result.openskimap_trail_count} reference trails)")

    if result.sample_trails:
        print("\n   Sample trails:")
        for trail in result.sample_trails:
            diff_str = f" [{trail.difficulty}]" if trail.difficulty else ""
            print(f"   • {trail.name}{diff_str}: {trail.status or 'unknown'}")


def print_summary(summary: TestSummary) -> None:
    """Print the test summary."""
    print(f"\n{'='*70}")
    print("📋 TEST SUMMARY")
    print(f"{'='*70}")
    print(f"Timestamp: {summary.timestamp}")
    print(f"Total resorts tested: {summary.total_resorts}")
    print(f"✅ Passing: {summary.passing_resorts}")
    print(f"❌ Failing: {summary.failing_resorts}")

    if summary.passing_resorts > 0:
        # Calculate averages for passing resorts
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
    parser = argparse.ArgumentParser(description="Test ski resort status configurations")
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

    # Load status pages
    entries = load_status_pages()
    if not entries:
        print("❌ No status pages configured in data/status_pages.csv")
        sys.exit(1)

    # Filter by resort ID if specified
    if args.resort_id:
        entries = [e for e in entries if e.resort_id == args.resort_id]
        if not entries:
            print(f"❌ Resort ID not found: {args.resort_id}")
            sys.exit(1)

    # Load reference data
    print("Loading OpenSkiMap reference data...")
    reference_lifts = load_lifts()
    reference_runs = load_runs()
    print(f"  Loaded {len(reference_lifts)} lifts and {len(reference_runs)} runs")

    # Test each resort
    print(f"\nTesting {len(entries)} resort(s)...\n")

    summary = TestSummary(
        timestamp=datetime.utcnow().isoformat() + "Z",
        total_resorts=len(entries),
    )

    for entry in entries:
        if not args.quiet:
            print(f"Testing {entry.resort_name}...")

        result = await test_resort(entry, reference_lifts, reference_runs)
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
        print(f"\n📁 Results saved to: {args.output}")

    # Output badge JSON if requested
    if args.badge_output:
        badge_data = generate_badge_json(summary)
        with open(args.badge_output, "w") as f:
            json.dump(badge_data, f, indent=2)
        print(f"📛 Badge JSON saved to: {args.badge_output}")

    # Exit with error code if any failures
    sys.exit(0 if summary.failing_resorts == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
