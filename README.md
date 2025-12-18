# Ski Lift Status

A Python library for fetching ski resort data from [OpenSkiMap](https://openskimap.org/).

## Overview

This library fetches and processes ski resort data from OpenSkiMap, including:
- Ski resorts/areas
- Ski lifts
- Ski runs

The data is fetched from OpenSkiMap's CSV exports and saved locally in the `data/` directory.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Fetching Data

Run the fetch script to download the latest data from OpenSkiMap:

```bash
python scripts/fetch_data.py
```

This will create three CSV files in the `data/` directory:
- `resorts.csv` - All ski resorts
- `lifts.csv` - All ski lifts
- `runs.csv` - All ski runs

### Using the Library

```python
import asyncio
from ski_lift_status import (
    fetch_and_save_all_data,
    load_resorts,
    load_lifts,
    load_runs,
    get_lifts_for_resort,
    get_runs_for_resort,
)

# Fetch latest data
asyncio.run(fetch_and_save_all_data())

# Load data
resorts = load_resorts()
lifts = load_lifts()
runs = load_runs()

# Get lifts for a specific resort
resort_id = "some-resort-id"
resort_lifts = get_lifts_for_resort(resort_id)
resort_runs = get_runs_for_resort(resort_id)
```

## GitHub Actions

The project includes a GitHub Actions workflow that automatically fetches data weekly:

- **Get Ski Resort Data** (`.github/workflows/get_ski_resort_data.yml`)
  - Runs weekly on Sundays at midnight
  - Can be manually triggered via workflow dispatch
  - Commits updated data files to the repository

## Data Structure

### Resort

- `id` - Unique identifier
- `name` - Resort name
- `countries` - Country/countries
- `status` - Operating status
- `regions` - Geographic regions (optional)
- `websites` - Resort website URLs (optional)

### Lift

- `id` - Unique identifier
- `name` - Lift name
- `lift_type` - Type of lift (e.g., gondola, chair_lift)
- `status` - Operating status
- `countries` - Country/countries
- `regions` - Geographic regions
- `localities` - Local areas
- `ski_area_names` - Associated resort names
- `ski_area_ids` - Associated resort IDs

### Run

- `id` - Unique identifier
- `name` - Run name
- `run_type` - Type of run
- `difficulty` - Difficulty level
- `status` - Operating status
- `countries` - Country/countries
- `regions` - Geographic regions
- `localities` - Local areas
- `ski_area_names` - Associated resort names
- `ski_area_ids` - Associated resort IDs

## License

MIT License - see LICENSE file for details.

## Data Source

Data is sourced from [OpenSkiMap](https://openskimap.org/), an open-source collaborative project for skiing and winter sports.
