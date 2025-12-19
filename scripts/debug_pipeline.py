#!/usr/bin/env python3
"""Debug the config pipeline step by step."""

import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ski_lift_status.config_pipeline.capture import capture_page_traffic
from ski_lift_status.config_pipeline.analysis import (
    load_lifts_for_resort,
    load_runs_for_resort,
    analyze_resources_for_lifts,
    analyze_resources_for_status,
)
from ski_lift_status.config_pipeline.config import generate_config, run_config, AnalysisContext


async def main():
    resort_id = "721dd142d0af653027c7569e1bd0799586bdefa1"
    data_dir = Path("data")

    print("=" * 60)
    print("Step 1: Load reference data")
    print("=" * 60)
    lifts = load_lifts_for_resort(resort_id, data_dir / "lifts.csv")
    runs = load_runs_for_resort(resort_id, data_dir / "runs.csv")
    print(f"Loaded {len(lifts)} lifts, {len(runs)} runs")

    # Get status page URL from status_pages.csv
    import csv
    status_url = None
    with open(data_dir / "status_pages.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("resort_id") == resort_id:
                status_url = row.get("status_page_url")
                break

    if not status_url:
        print("No status page found!")
        return

    print(f"Status URL: {status_url}")

    print("\n" + "=" * 60)
    print("Step 2: Capture page traffic")
    print("=" * 60)
    traffic = await capture_page_traffic(status_url)
    print(f"Page HTML: {len(traffic.page_html or '')} bytes")
    print(f"Resources: {len(traffic.resources)}")
    for r in traffic.resources[:5]:
        print(f"  - {r.resource_type.value}: {r.url[:60]}... ({r.body_size} bytes)")

    print("\n" + "=" * 60)
    print("Step 3: Analyze for lifts")
    print("=" * 60)
    # Convert resources to dicts for analysis
    resource_dicts = [r.to_dict() for r in traffic.resources]
    lift_results = analyze_resources_for_lifts(resource_dicts, lifts)
    print(f"Analyzed {len(lift_results)} resources")
    for result in sorted(lift_results, key=lambda r: r.coverage_percent, reverse=True)[:3]:
        print(f"  - {result.resource_url[:50]}... Coverage: {result.coverage_percent:.1f}%")
        if result.matches:
            print(f"    Matches: {[m.lift_name for m in result.matches[:5]]}")

    # Check page HTML directly
    from ski_lift_status.config_pipeline.analysis import find_lift_names_in_content
    html_matches = find_lift_names_in_content(traffic.page_html or "", lifts)
    print(f"\nPage HTML matches: {len(html_matches)}")
    if html_matches:
        print(f"  Matched lifts: {[m.lift_name for m in html_matches[:10]]}")

    print("\n" + "=" * 60)
    print("Step 4: Build context and generate config")
    print("=" * 60)

    # Build simple context
    context = AnalysisContext(
        resort_id=resort_id,
        resort_name="Alpe d'Huez Grand Domaine",
    )

    # Add best resource URL
    if lift_results:
        best = max(lift_results, key=lambda r: r.coverage_percent)
        if best.coverage_percent > 0:
            context.lift_static_url = best.resource_url
            print(f"Best lift resource: {best.resource_url}")
        else:
            context.lift_static_url = status_url
            print("No good lift resource found, using status URL")

    result = await generate_config(context, max_attempts=1)
    print(f"\nGeneration success: {result.success}")
    print(f"Errors: {result.errors}")

    if result.config:
        print("\nGenerated config:")
        print(json.dumps(result.config.to_dict(), indent=2)[:2000])

        print("\n" + "=" * 60)
        print("Step 5: Test config")
        print("=" * 60)
        test_result = await run_config(result.config)
        print(f"Execution success: {test_result.success}")
        print(f"Extracted lifts: {len(test_result.lifts)}")
        print(f"Extracted runs: {len(test_result.runs)}")
        print(f"Errors: {test_result.errors}")
        if test_result.lifts:
            print("Sample lifts:")
            for lift in test_result.lifts[:5]:
                print(f"  - {lift.source_name}: {lift.status}")


if __name__ == "__main__":
    asyncio.run(main())
