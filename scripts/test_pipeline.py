#!/usr/bin/env python3
"""Test the config pipeline with a real resort."""

import asyncio
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ski_lift_status.config_pipeline import run_pipeline


async def main():
    # Test with Alpe d'Huez
    resort_id = "721dd142d0af653027c7569e1bd0799586bdefa1"

    print(f"Running pipeline for resort: {resort_id}")
    print("=" * 60)

    result = await run_pipeline(
        resort_id=resort_id,
        data_dir="data",
        max_attempts=3,
    )

    print(f"\nResult:")
    print(f"  Success: {result.success}")
    print(f"  Resort: {result.resort_name}")
    print(f"  Lift Coverage: {result.lift_coverage:.1f}%")
    print(f"  Run Coverage: {result.run_coverage:.1f}%")

    if result.errors:
        print(f"\nErrors:")
        for err in result.errors:
            print(f"  - {err}")

    if result.config:
        print(f"\nConfig generated:")
        print(f"  Sources: {len(result.config.sources)}")
        for i, source in enumerate(result.config.sources):
            print(f"    [{i}] URL: {source.url[:80]}...")
            print(f"        Method: {source.extraction_method.value}")
            print(f"        Types: {source.data_types}")
            print(f"        List selector: {source.list_selector[:50]}..." if source.list_selector else "        List selector: (none)")
        print(f"  Lift mappings: {len(result.config.lift_mappings)}")
        print(f"  Run mappings: {len(result.config.run_mappings)}")

        # Save config
        output_path = Path("data/generated_configs") / f"{resort_id}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(result.config.to_json())
        print(f"\nConfig saved to: {output_path}")

    if result.debug_info:
        print(f"\nDebug info:")
        print(f"  Attempts: {result.debug_info.get('attempts', 0)}")

        lift_results = result.debug_info.get('lift_match_results', [])
        if lift_results:
            print(f"  Best lift resource coverage: {lift_results[0].get('coverage_percent', 0):.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
