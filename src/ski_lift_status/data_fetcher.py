"""Data fetcher module for downloading and processing OpenSkiMap data."""

import csv
from io import StringIO
from pathlib import Path

import httpx
import pandas as pd

from .models import Lift, Resort, Run
from .utils import get_data_dir, model_to_dict

# OpenSkiMap CSV URLs
OPENSKIMAP_BASE_URL = "https://tiles.openskimap.org/csv"
SKI_AREAS_URL = f"{OPENSKIMAP_BASE_URL}/ski_areas.csv"
LIFTS_URL = f"{OPENSKIMAP_BASE_URL}/lifts.csv"
RUNS_URL = f"{OPENSKIMAP_BASE_URL}/runs.csv"


async def fetch_csv(url: str, timeout: float = 120.0) -> str:
    """Fetch CSV content from a URL."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


def parse_ski_areas_csv(csv_content: str) -> list[Resort]:
    """Parse ski areas CSV into Resort objects."""
    df = pd.read_csv(StringIO(csv_content), dtype=str)
    df = df.fillna("")

    resorts = []
    for _, row in df.iterrows():
        resort = Resort(
            id=row.get("id", ""),
            name=row.get("name", ""),
            countries=row.get("countries", ""),
            status=row.get("status", ""),
            regions=row.get("regions", "") or None,
            websites=row.get("websites", "") or None,
        )
        resorts.append(resort)

    return resorts


def parse_lifts_csv(csv_content: str) -> list[Lift]:
    """Parse lifts CSV into Lift objects."""
    df = pd.read_csv(StringIO(csv_content), dtype=str)
    df = df.fillna("")

    lifts = []
    for _, row in df.iterrows():
        lift = Lift(
            id=row.get("id", ""),
            name=row.get("name", "") or None,
            lift_type=row.get("lift_type", "") or None,
            status=row.get("status", "") or None,
            countries=row.get("countries", "") or None,
            regions=row.get("regions", "") or None,
            localities=row.get("localities", "") or None,
            ski_area_names=row.get("ski_area_names", "") or None,
            ski_area_ids=row.get("ski_area_ids", "") or None,
        )
        lifts.append(lift)

    return lifts


def parse_runs_csv(csv_content: str) -> list[Run]:
    """Parse runs CSV into Run objects."""
    df = pd.read_csv(StringIO(csv_content), dtype=str)
    df = df.fillna("")

    runs = []
    for _, row in df.iterrows():
        run = Run(
            id=row.get("id", ""),
            name=row.get("name", "") or None,
            run_type=row.get("use", "") or None,  # 'use' column contains type info
            difficulty=row.get("difficulty", "") or None,
            status=row.get("status", "") or None,
            countries=row.get("countries", "") or None,
            regions=row.get("regions", "") or None,
            localities=row.get("localities", "") or None,
            ski_area_names=row.get("ski_area_names", "") or None,
            ski_area_ids=row.get("ski_area_ids", "") or None,
        )
        runs.append(run)

    return runs


def save_resorts_csv(resorts: list[Resort], output_path: Path | None = None) -> Path:
    """Save resorts to CSV file."""
    if output_path is None:
        output_path = get_data_dir() / "resorts.csv"

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["id", "name", "countries", "status", "regions", "websites"]
        )
        writer.writeheader()
        for resort in resorts:
            writer.writerow(model_to_dict(resort))

    return output_path


def save_lifts_csv(lifts: list[Lift], output_path: Path | None = None) -> Path:
    """Save lifts to CSV file."""
    if output_path is None:
        output_path = get_data_dir() / "lifts.csv"

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "name",
                "lift_type",
                "status",
                "countries",
                "regions",
                "localities",
                "ski_area_names",
                "ski_area_ids",
            ],
        )
        writer.writeheader()
        for lift in lifts:
            writer.writerow(model_to_dict(lift))

    return output_path


def save_runs_csv(runs: list[Run], output_path: Path | None = None) -> Path:
    """Save runs to CSV file."""
    if output_path is None:
        output_path = get_data_dir() / "runs.csv"

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "name",
                "run_type",
                "difficulty",
                "status",
                "countries",
                "regions",
                "localities",
                "ski_area_names",
                "ski_area_ids",
            ],
        )
        writer.writeheader()
        for run in runs:
            writer.writerow(model_to_dict(run))

    return output_path


async def fetch_and_save_all_data() -> dict[str, Path]:
    """Fetch all data from OpenSkiMap and save to CSV files."""
    print("Fetching ski areas data...")
    ski_areas_csv = await fetch_csv(SKI_AREAS_URL)
    resorts = parse_ski_areas_csv(ski_areas_csv)
    resorts_path = save_resorts_csv(resorts)
    print(f"Saved {len(resorts)} resorts to {resorts_path}")

    print("Fetching lifts data...")
    lifts_csv = await fetch_csv(LIFTS_URL)
    lifts = parse_lifts_csv(lifts_csv)
    lifts_path = save_lifts_csv(lifts)
    print(f"Saved {len(lifts)} lifts to {lifts_path}")

    print("Fetching runs data...")
    runs_csv = await fetch_csv(RUNS_URL)
    runs = parse_runs_csv(runs_csv)
    runs_path = save_runs_csv(runs)
    print(f"Saved {len(runs)} runs to {runs_path}")

    return {"resorts": resorts_path, "lifts": lifts_path, "runs": runs_path}


def load_resorts(path: Path | None = None) -> list[Resort]:
    """Load resorts from CSV file."""
    if path is None:
        path = get_data_dir() / "resorts.csv"

    if not path.exists():
        return []

    resorts = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            resorts.append(Resort(**row))

    return resorts


def load_lifts(path: Path | None = None) -> list[Lift]:
    """Load lifts from CSV file."""
    if path is None:
        path = get_data_dir() / "lifts.csv"

    if not path.exists():
        return []

    lifts = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lifts.append(Lift(**row))

    return lifts


def load_runs(path: Path | None = None) -> list[Run]:
    """Load runs from CSV file."""
    if path is None:
        path = get_data_dir() / "runs.csv"

    if not path.exists():
        return []

    runs = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            runs.append(Run(**row))

    return runs


def get_lifts_for_resort(resort_id: str, lifts: list[Lift] | None = None) -> list[Lift]:
    """Get all lifts for a specific resort."""
    if lifts is None:
        lifts = load_lifts()

    return [lift for lift in lifts if resort_id in (lift.ski_area_ids or "").split(";")]


def get_runs_for_resort(resort_id: str, runs: list[Run] | None = None) -> list[Run]:
    """Get all runs for a specific resort."""
    if runs is None:
        runs = load_runs()

    return [run for run in runs if resort_id in (run.ski_area_ids or "").split(";")]


def get_resort_by_id(resort_id: str, resorts: list[Resort] | None = None) -> Resort | None:
    """Get a resort by its ID."""
    if resorts is None:
        resorts = load_resorts()

    for resort in resorts:
        if resort.id == resort_id:
            return resort

    return None

