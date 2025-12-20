#!/usr/bin/env python3
"""Script to fetch ski resort data from OpenSkiMap.

Downloads resort, lift, and run data from OpenSkiMap's static exports
and saves them as CSV files in the data/ directory.
"""

import asyncio
import csv
from pathlib import Path

import httpx

# OpenSkiMap export URLs
OPENSKIMAP_BASE = "https://tiles.openskimap.org/data"
ENDPOINTS = {
    "resorts": f"{OPENSKIMAP_BASE}/ski_areas_enriched.geojson",
    "lifts": f"{OPENSKIMAP_BASE}/lifts.geojson",
    "runs": f"{OPENSKIMAP_BASE}/runs.geojson",
}

DATA_DIR = Path(__file__).parent.parent / "data"


async def fetch_geojson(client: httpx.AsyncClient, url: str) -> dict:
    """Fetch GeoJSON data from URL."""
    print(f"Fetching {url}...")
    response = await client.get(url, timeout=120.0)
    response.raise_for_status()
    return response.json()


def extract_resort_properties(feature: dict) -> dict:
    """Extract relevant properties from a ski area feature."""
    props = feature.get("properties", {})
    return {
        "id": props.get("id", ""),
        "name": props.get("name", ""),
        "countries": ";".join(props.get("location", {}).get("country", {}).get("name", [])) if isinstance(props.get("location", {}).get("country", {}).get("name"), list) else props.get("location", {}).get("country", {}).get("name", ""),
        "status": props.get("status", ""),
        "regions": ";".join(props.get("location", {}).get("region", {}).get("name", [])) if isinstance(props.get("location", {}).get("region", {}).get("name"), list) else props.get("location", {}).get("region", {}).get("name", ""),
        "websites": ";".join(props.get("websites", [])) if props.get("websites") else "",
    }


def extract_lift_properties(feature: dict) -> dict:
    """Extract relevant properties from a lift feature."""
    props = feature.get("properties", {})
    ski_areas = props.get("skiAreas", []) or []
    return {
        "id": props.get("id", ""),
        "name": props.get("name", ""),
        "lift_type": props.get("liftType", ""),
        "status": props.get("status", ""),
        "countries": ";".join([loc.get("country", {}).get("name", "") for loc in [props.get("location", {})] if loc.get("country")]),
        "regions": ";".join([loc.get("region", {}).get("name", "") for loc in [props.get("location", {})] if loc.get("region")]),
        "localities": ";".join(props.get("location", {}).get("locales", [])) if props.get("location", {}).get("locales") else "",
        "ski_area_names": ";".join([sa.get("properties", {}).get("name", "") for sa in ski_areas]),
        "ski_area_ids": ";".join([sa.get("properties", {}).get("id", "") for sa in ski_areas]),
    }


def extract_run_properties(feature: dict) -> dict:
    """Extract relevant properties from a run feature."""
    props = feature.get("properties", {})
    ski_areas = props.get("skiAreas", []) or []
    return {
        "id": props.get("id", ""),
        "name": props.get("name", ""),
        "difficulty": props.get("difficulty", ""),
        "status": props.get("status", ""),
        "grooming": props.get("grooming", ""),
        "lit": props.get("lit", ""),
        "ski_area_names": ";".join([sa.get("properties", {}).get("name", "") for sa in ski_areas]),
        "ski_area_ids": ";".join([sa.get("properties", {}).get("id", "") for sa in ski_areas]),
    }


async def fetch_and_save_all_data() -> dict[str, Path]:
    """Fetch all data from OpenSkiMap and save to CSV files."""
    DATA_DIR.mkdir(exist_ok=True)
    results = {}

    async with httpx.AsyncClient() as client:
        # Fetch all data in parallel
        resorts_data, lifts_data, runs_data = await asyncio.gather(
            fetch_geojson(client, ENDPOINTS["resorts"]),
            fetch_geojson(client, ENDPOINTS["lifts"]),
            fetch_geojson(client, ENDPOINTS["runs"]),
        )

        # Process resorts
        resorts_path = DATA_DIR / "resorts.csv"
        resorts = [extract_resort_properties(f) for f in resorts_data.get("features", [])]
        if resorts:
            with open(resorts_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=resorts[0].keys())
                writer.writeheader()
                writer.writerows(resorts)
            results["resorts"] = resorts_path
            print(f"Saved {len(resorts)} resorts to {resorts_path}")

        # Process lifts
        lifts_path = DATA_DIR / "lifts.csv"
        lifts = [extract_lift_properties(f) for f in lifts_data.get("features", [])]
        if lifts:
            with open(lifts_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=lifts[0].keys())
                writer.writeheader()
                writer.writerows(lifts)
            results["lifts"] = lifts_path
            print(f"Saved {len(lifts)} lifts to {lifts_path}")

        # Process runs
        runs_path = DATA_DIR / "runs.csv"
        runs = [extract_run_properties(f) for f in runs_data.get("features", [])]
        if runs:
            with open(runs_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=runs[0].keys())
                writer.writeheader()
                writer.writerows(runs)
            results["runs"] = runs_path
            print(f"Saved {len(runs)} runs to {runs_path}")

    return results


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
