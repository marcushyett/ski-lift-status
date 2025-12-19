#!/usr/bin/env python3
"""Autonomous config builder script.

This script uses the fully autonomous config builder agent to discover
and build configurations for ski resort status pages.

Usage:
    # Build configs for all resorts in status_pages.csv
    python scripts/build_configs.py

    # Build config for a specific resort
    python scripts/build_configs.py --resort-id abc123

    # Build configs for top N resorts
    python scripts/build_configs.py --limit 10

    # Override existing configs
    python scripts/build_configs.py --override

    # Use specific CSV file
    python scripts/build_configs.py --csv data/custom_resorts.csv
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ski_lift_status.scraping.config_builder import (
    AutonomousConfigBuilder,
    build_config_for_resort,
    build_configs_from_csv,
    ConfigBuildResult,
)
from ski_lift_status.scraping.resort_config import save_resort_config


def print_result(result: ConfigBuildResult) -> None:
    """Print a formatted result summary."""
    status = "SUCCESS" if result.success else "FAILED"
    print(f"\n{'='*60}")
    print(f"Resort: {result.resort_name}")
    print(f"Status: {status}")
    print(f"URL: {result.status_page_url}")

    if result.success:
        print(f"Platform: {result.platform_hint}")
        print(f"Confidence: {result.confidence:.1%}")
        if result.validation_result:
            print(f"Lifts: {result.validation_result.get('lift_count', 0)}")
            print(f"Trails: {result.validation_result.get('trail_count', 0)}")
    else:
        print(f"Errors: {', '.join(result.errors)}")

    if result.reasoning:
        print(f"Reasoning: {result.reasoning[:200]}...")

    print(f"{'='*60}")


async def build_single_resort(
    resort_id: str,
    resort_name: str,
    status_page_url: str,
    output_dir: Path | None = None,
) -> ConfigBuildResult:
    """Build config for a single resort."""
    print(f"\nBuilding config for: {resort_name}")
    print(f"Status page: {status_page_url}")

    result = await build_config_for_resort(
        resort_id=resort_id,
        resort_name=resort_name,
        status_page_url=status_page_url,
    )

    if result.success and result.config:
        # Save the config
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"{resort_id}.json"
            save_resort_config(result.config, path)
            print(f"Config saved to: {path}")
        else:
            path = save_resort_config(result.config)
            print(f"Config saved to: {path}")

        # Also save the extraction code if custom platform
        if result.extraction_code:
            code_path = (output_dir or Path("data/resort_configs")) / f"{resort_id}_extractor.py"
            code_path.parent.mkdir(parents=True, exist_ok=True)
            with open(code_path, "w") as f:
                f.write(result.extraction_code)
            print(f"Extraction code saved to: {code_path}")

    print_result(result)
    return result


async def build_from_csv(
    csv_path: Path,
    output_dir: Path | None = None,
    skip_existing: bool = True,
    limit: int | None = None,
) -> list[ConfigBuildResult]:
    """Build configs for all resorts in CSV."""
    import csv

    print(f"\nReading resorts from: {csv_path}")

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        entries = list(reader)

    total = len(entries)
    if limit:
        entries = entries[:limit]
        print(f"Processing {len(entries)} of {total} resorts (limited)")
    else:
        print(f"Processing {total} resorts")

    results = []
    agent = AutonomousConfigBuilder()

    for i, entry in enumerate(entries, 1):
        resort_id = entry.get("resort_id", "").strip()
        resort_name = entry.get("resort_name", "").strip()
        status_page_url = entry.get("status_page_url", "").strip()

        if not resort_id or not status_page_url:
            continue

        print(f"\n[{i}/{len(entries)}] Processing: {resort_name}")

        try:
            result = await agent.build(
                resort_id=resort_id,
                resort_name=resort_name,
                status_page_url=status_page_url,
                website_url=entry.get("website_url"),
            )
            results.append(result)

            if result.success and result.config:
                # Save config
                if output_dir:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    path = output_dir / f"{resort_id}.json"
                else:
                    path = None
                save_resort_config(result.config, path)

                # Save extraction code
                if result.extraction_code:
                    code_dir = output_dir or Path("data/resort_configs")
                    code_path = code_dir / f"{resort_id}_extractor.py"
                    code_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(code_path, "w") as f:
                        f.write(result.extraction_code)

            print_result(result)

        except Exception as e:
            print(f"ERROR: {e}")
            results.append(ConfigBuildResult(
                resort_id=resort_id,
                resort_name=resort_name,
                status_page_url=status_page_url,
                success=False,
                errors=[str(e)],
            ))

        # Rate limiting
        await asyncio.sleep(2.0)

    return results


def print_summary(results: list[ConfigBuildResult]) -> None:
    """Print a summary of all results."""
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total processed: {len(results)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")

    if successful:
        print("\nSuccessful resorts:")
        for r in successful:
            print(f"  - {r.resort_name} ({r.platform_hint})")

    if failed:
        print("\nFailed resorts:")
        for r in failed:
            print(f"  - {r.resort_name}: {r.errors[0] if r.errors else 'Unknown error'}")

    print("="*60)


async def main():
    parser = argparse.ArgumentParser(
        description="Autonomous config builder for ski resort status pages"
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("data/status_pages.csv"),
        help="Path to CSV file with resort data",
    )
    parser.add_argument(
        "--resort-id",
        type=str,
        help="Build config for a specific resort ID only",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of resorts to process",
    )
    parser.add_argument(
        "--override",
        action="store_true",
        help="Override existing configs",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory to save configs",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Save results summary to JSON file",
    )

    args = parser.parse_args()

    results = []

    if args.resort_id:
        # Build for specific resort - need to look up in CSV
        import csv
        with open(args.csv, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("resort_id", "").strip() == args.resort_id:
                    result = await build_single_resort(
                        resort_id=row["resort_id"].strip(),
                        resort_name=row["resort_name"].strip(),
                        status_page_url=row["status_page_url"].strip(),
                        output_dir=args.output_dir,
                    )
                    results.append(result)
                    break
            else:
                print(f"Resort ID not found: {args.resort_id}")
                sys.exit(1)
    else:
        # Build from CSV
        results = await build_from_csv(
            csv_path=args.csv,
            output_dir=args.output_dir,
            skip_existing=not args.override,
            limit=args.limit,
        )

    print_summary(results)

    # Save results to JSON if requested
    if args.output_json:
        output_data = []
        for r in results:
            output_data.append({
                "resort_id": r.resort_id,
                "resort_name": r.resort_name,
                "status_page_url": r.status_page_url,
                "success": r.success,
                "platform_hint": r.platform_hint,
                "confidence": r.confidence,
                "validation_result": r.validation_result,
                "errors": r.errors,
            })

        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output_json, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\nResults saved to: {args.output_json}")

    # Exit with error if any failed
    if any(not r.success for r in results):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
