#!/usr/bin/env python3
"""Inspect embedded scripts and API data in a ski resort status page."""

import asyncio
import sys
import re
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ski_lift_status.config_pipeline.capture import capture_page_traffic


async def main():
    url = "https://www.seealpedhuez.com/lifts/status"

    print(f"Capturing: {url}")
    traffic = await capture_page_traffic(url)

    html = traffic.page_html or ""

    # Find all script tags with content
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.IGNORECASE | re.DOTALL)
    print(f"\nFound {len(scripts)} script tags")

    # Look for inline data
    for i, script in enumerate(scripts):
        if len(script) < 100:
            continue

        # Look for JSON-like data
        if '{' in script and ('"lifts"' in script.lower() or '"status"' in script.lower() or
                               'lift' in script.lower() or 'ouvert' in script.lower() or 'fermé' in script.lower()):
            print(f"\n=== Script {i} (potential lift data) ===")
            print(script[:500])
            print("...")

    # Check captured resources
    print("\n\n=== Captured Resources ===")
    for r in traffic.resources:
        print(f"\n{r.resource_type.value}: {r.url}")
        if r.body:
            print(f"  Size: {len(r.body)} bytes")
            # Try to parse as JSON
            try:
                data = json.loads(r.body)
                print(f"  JSON structure: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
                if isinstance(data, dict):
                    print(f"  Sample: {json.dumps(data, indent=2)[:300]}...")
            except:
                print(f"  Content preview: {r.body[:200]}...")


if __name__ == "__main__":
    asyncio.run(main())
