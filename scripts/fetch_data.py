#!/usr/bin/env python3
"""Script to fetch ski resort data from OpenSkiMap."""

import asyncio
import sys
from pathlib import Path

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ski_lift_status.data_fetcher import fetch_and_save_all_data


async def main():
    """Main entry point."""
    print("=" * 60)
    print("Fetching ski resort data from OpenSkiMap")
    print("=" * 60)

    result = await fetch_and_save_all_data()

    print("\n" + "=" * 60)
    print("Data fetched successfully!")
    print("=" * 60)
    print("\nFiles saved:")
    for name, path in result.items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    asyncio.run(main())


