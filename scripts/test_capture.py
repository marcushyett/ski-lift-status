#!/usr/bin/env python3
"""Test the BrowserQL traffic capture directly."""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ski_lift_status.config_pipeline.capture import capture_page_traffic


async def main():
    url = "https://www.seealpedhuez.com/lifts/status"

    api_key = os.environ.get("BROWSERLESS_API_KEY")
    print(f"Testing BrowserQL capture for: {url}")
    print(f"BROWSERLESS_API_KEY set: {bool(api_key)}")

    if not api_key:
        print("No API key found!")
        return

    print("\nCapturing page traffic...")
    traffic = await capture_page_traffic(url)

    if traffic.errors:
        print(f"\nErrors:")
        for err in traffic.errors:
            print(f"  - {err}")
        return

    print(f"\nCapture Results:")
    print(f"  Final URL: {traffic.final_url}")
    print(f"  Load time: {traffic.load_time_ms:.0f}ms")
    print(f"  Page HTML length: {len(traffic.page_html) if traffic.page_html else 0}")
    print(f"  Total resources: {len(traffic.resources)}")
    print(f"  XHR resources: {len(traffic.xhr_resources)}")
    print(f"  JSON resources: {len(traffic.json_resources)}")
    print(f"  Resources with body: {len(traffic.get_resources_with_body())}")

    # Show sample resources
    if traffic.json_resources:
        print(f"\nJSON Resources found:")
        for r in traffic.json_resources[:5]:
            print(f"  - {r.url[:80]}... ({r.body_size} bytes)")

    if traffic.xhr_resources:
        print(f"\nXHR Resources found:")
        for r in traffic.xhr_resources[:5]:
            print(f"  - {r.url[:80]}... ({r.body_size} bytes)")

    print("\nSuccess!")


if __name__ == "__main__":
    asyncio.run(main())
