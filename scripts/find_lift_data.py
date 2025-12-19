#!/usr/bin/env python3
"""Find lift status data patterns in page HTML."""

import asyncio
import sys
import re
from pathlib import Path
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ski_lift_status.config_pipeline.capture import capture_page_traffic


async def main():
    url = "https://www.seealpedhuez.com/lifts/status"

    print(f"Capturing: {url}")
    traffic = await capture_page_traffic(url)

    html = traffic.page_html or ""
    print(f"HTML length: {len(html)} bytes")

    # Parse with BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')

    # Look for list/table structures
    print("\n=== Tables ===")
    tables = soup.find_all('table')
    print(f"Found {len(tables)} tables")
    for i, table in enumerate(tables[:5]):
        rows = table.find_all('tr')
        print(f"  Table {i}: {len(rows)} rows")
        for row in rows[:3]:
            cells = row.find_all(['td', 'th'])
            print(f"    Row: {[c.get_text(strip=True)[:30] for c in cells]}")

    # Look for lists
    print("\n=== Unordered Lists with many items ===")
    lists = soup.find_all('ul')
    big_lists = [l for l in lists if len(l.find_all('li')) > 5]
    print(f"Found {len(big_lists)} lists with >5 items")
    for i, ul in enumerate(big_lists[:3]):
        items = ul.find_all('li')
        print(f"  List {i}: {len(items)} items")
        for item in items[:3]:
            text = item.get_text(strip=True)[:60]
            print(f"    - {text}")

    # Look for divs/sections with repeated structure
    print("\n=== Common class patterns ===")
    all_elements = soup.find_all(class_=True)
    class_counts = {}
    for el in all_elements:
        for cls in el.get('class', []):
            class_counts[cls] = class_counts.get(cls, 0) + 1

    # Show classes that appear many times (might be list items)
    repeated_classes = [(k, v) for k, v in class_counts.items() if v >= 5 and v <= 100]
    repeated_classes.sort(key=lambda x: x[1], reverse=True)
    print("Classes appearing 5-100 times:")
    for cls, count in repeated_classes[:20]:
        print(f"  .{cls}: {count} occurrences")

    # Look for status-related text in structured elements
    print("\n=== Elements containing status words ===")
    status_words = ['open', 'closed', 'fermé', 'ouvert', 'offen', 'geschlossen']
    for word in status_words:
        elements = soup.find_all(string=re.compile(word, re.IGNORECASE))
        if elements:
            print(f"\n'{word}' found in {len(elements)} places:")
            for el in elements[:3]:
                parent = el.parent
                print(f"  Tag: {parent.name}, Class: {parent.get('class', [])}")
                print(f"  Text: {el[:50]}...")

    # Look for lift-named sections
    print("\n=== Sections with lift names ===")
    lift_terms = ['télésiège', 'télécabine', 'gondola', 'chairlift', 'téléski', 'cable car']
    for term in lift_terms:
        elements = soup.find_all(string=re.compile(term, re.IGNORECASE))
        if elements:
            print(f"\n'{term}' found in {len(elements)} places:")
            for el in elements[:2]:
                parent = el.parent
                print(f"  Tag: {parent.name}, Text: {str(el)[:80]}...")


if __name__ == "__main__":
    asyncio.run(main())
