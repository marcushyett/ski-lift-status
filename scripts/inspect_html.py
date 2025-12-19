#!/usr/bin/env python3
"""Inspect the HTML structure of a ski resort status page."""

import asyncio
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ski_lift_status.config_pipeline.capture import capture_page_traffic


async def main():
    url = "https://www.seealpedhuez.com/lifts/status"

    print(f"Capturing: {url}")
    traffic = await capture_page_traffic(url)

    html = traffic.page_html or ""
    print(f"\nPage HTML length: {len(html)} bytes")

    # Look for lift-related patterns
    patterns = [
        (r'class="[^"]*lift[^"]*"', "Classes containing 'lift'"),
        (r'class="[^"]*status[^"]*"', "Classes containing 'status'"),
        (r'class="[^"]*remontée[^"]*"', "Classes containing 'remontée'"),
        (r'<(?:div|li|tr|article)[^>]*(?:lift|status)[^>]*>', "Elements with lift/status"),
    ]

    for pattern, desc in patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)
        if matches:
            print(f"\n{desc}:")
            for m in set(matches)[:10]:
                print(f"  {m[:100]}")

    # Find sections that might contain lift data
    print("\n\nSearching for lift names in context...")
    lift_names = ["Pic Blanc", "Marmottes", "Chalvet", "Rif Nel", "Villarais"]

    for name in lift_names:
        matches = list(re.finditer(re.escape(name), html, re.IGNORECASE))
        if matches:
            print(f"\nFound '{name}' at {len(matches)} positions:")
            for m in matches[:2]:
                start = max(0, m.start() - 200)
                end = min(len(html), m.end() + 200)
                context = html[start:end]
                # Clean up
                context = re.sub(r'\s+', ' ', context)
                print(f"  ...{context}...")
                break


if __name__ == "__main__":
    asyncio.run(main())
