#!/usr/bin/env python3
"""Test the analysis pipeline without LLM generation."""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ski_lift_status.config_pipeline.capture import capture_page_traffic
from ski_lift_status.config_pipeline.analysis import (
    load_lifts_for_resort,
    load_runs_for_resort,
    find_lift_names_in_content,
    find_run_names_in_content,
    find_status_indicators,
)


async def main():
    resort_id = "721dd142d0af653027c7569e1bd0799586bdefa1"
    url = "https://www.seealpedhuez.com/lifts/status"
    data_dir = "data"

    print(f"Testing analysis for resort: {resort_id}")
    print(f"URL: {url}")
    print("=" * 60)

    # Load reference data
    print("\n1. Loading reference data...")
    lifts_csv = Path(data_dir) / "lifts.csv"
    runs_csv = Path(data_dir) / "runs.csv"
    lifts = load_lifts_for_resort(resort_id, lifts_csv)
    runs = load_runs_for_resort(resort_id, runs_csv)
    print(f"   Loaded {len(lifts)} lifts and {len(runs)} runs from OpenSkiMap")

    if lifts:
        print(f"   Sample lifts: {[l['name'] for l in lifts[:5]]}")

    # Capture page traffic
    print("\n2. Capturing page traffic...")
    traffic = await capture_page_traffic(url)

    if traffic.errors:
        print(f"   Errors during capture: {traffic.errors}")
        return

    print(f"   Page HTML: {len(traffic.page_html or '')} bytes")
    print(f"   Resources captured: {len(traffic.resources)}")

    # Analyze page content for lift names
    print("\n3. Analyzing content for lift names...")

    # Check in page HTML - pass the full lift dicts, not just names
    html_matches = find_lift_names_in_content(traffic.page_html or "", lifts)
    print(f"   Found {len(html_matches)} lift names in page HTML")
    if html_matches:
        print(f"   Sample matches: {[m.lift_name for m in html_matches[:5]]}")

    # Check in captured resources
    for resource in traffic.resources[:10]:
        if resource.body:
            matches = find_lift_names_in_content(resource.body, lifts)
            if matches:
                print(f"   Found {len(matches)} lift names in {resource.url[:60]}...")
                print(f"      Matches: {[m.lift_name for m in matches[:3]]}")

    # Analyze for status words
    print("\n4. Analyzing for status words...")
    status_results = find_status_indicators(traffic.page_html or "")
    print(f"   Lift indicators: {status_results.lift_indicator_count}")
    print(f"   Run indicators: {status_results.run_indicator_count}")
    print(f"   Status word count: {status_results.status_word_count}")

    # Print a snippet of the HTML to understand the structure
    print("\n5. Sample of page HTML (for manual inspection)...")
    if traffic.page_html:
        # Find lift-related content
        import re
        lift_section = re.search(r'<div[^>]*class="[^"]*lift[^"]*"[^>]*>.*?</div>', traffic.page_html[:50000], re.IGNORECASE | re.DOTALL)
        if lift_section:
            print(f"   Found lift section: {lift_section.group()[:500]}...")
        else:
            # Look for any lift-related text
            lift_text = re.search(r'.{0,200}(télésiège|télécabine|téléphérique|gondola|chair).{0,200}', traffic.page_html, re.IGNORECASE)
            if lift_text:
                print(f"   Found lift-related text: {lift_text.group()[:300]}...")

    print("\n" + "=" * 60)
    print("Analysis complete!")


if __name__ == "__main__":
    asyncio.run(main())
