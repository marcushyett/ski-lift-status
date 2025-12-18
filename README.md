# Ski Lift Status

![Resort Configs](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/marcushyett/ski-lift-status/main/.github/badges/config-status.json)
[![CI](https://github.com/marcushyett/ski-lift-status/actions/workflows/ci.yml/badge.svg)](https://github.com/marcushyett/ski-lift-status/actions/workflows/ci.yml)

A Python library for fetching ski resort data from [OpenSkiMap](https://openskimap.org/) and scraping real-time status information from resort websites.

## Overview

This library provides two main capabilities:

1. **OpenSkiMap Data Fetching**: Fetches and processes ski resort data from OpenSkiMap, including resorts, lifts, and runs.

2. **Scraping Pipeline**: An AI-powered pipeline for automatically extracting real-time lift and run status from resort websites.

The data is fetched from OpenSkiMap's CSV exports and saved locally in the `data/` directory.

## Installation

```bash
pip install -r requirements.txt

# Install Playwright browsers for scraping
playwright install chromium
```

## Usage

### Fetching OpenSkiMap Data

Run the fetch script to download the latest data from OpenSkiMap:

```bash
python scripts/fetch_data.py
```

This will create three CSV files in the `data/` directory:
- `resorts.csv` - All ski resorts
- `lifts.csv` - All ski lifts
- `runs.csv` - All ski runs

### Using the Scraping Pipeline

The scraping pipeline automatically extracts lift and run status from resort websites:

```bash
# Run for a specific resort
python scripts/run_pipeline.py --resort-id <resort-id> --url <status-page-url>

# Run for all configured resorts
python scripts/run_pipeline.py --all

# Use mock LLM for testing (no API calls)
python scripts/run_pipeline.py --all --mock-llm
```

### Programmatic Usage

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
from ski_lift_status.scraping import (
    run_pipeline_for_resort,
    run_pipeline_for_all,
)

# Fetch OpenSkiMap data
asyncio.run(fetch_and_save_all_data())

# Load data
resorts = load_resorts()
lifts = load_lifts()
runs = load_runs()

# Get lifts for a specific resort
resort_id = "some-resort-id"
resort_lifts = get_lifts_for_resort(resort_id)
resort_runs = get_runs_for_resort(resort_id)

# Run scraping pipeline for a resort
result = asyncio.run(run_pipeline_for_resort(
    resort_id="68b126bc3175516c9263aed7635d14e37ff360dc",
    status_page_url="https://www.les3vallees.com/fr/live/ouverture-des-pistes-et-remontees",
    resort_name="Les Trois Vallées",
))

if result.success:
    print(f"Extracted {len(result.lifts_data)} lifts")
    print(f"Lift coverage: {result.lift_coverage:.1%}")
```

## Scraping Pipeline Architecture

The scraping pipeline consists of 6 phases:

### Phase 1: Data Collection
- Uses Playwright to load resort status pages
- Captures all network traffic (XHR requests, JavaScript files, HTML)
- Identifies resources containing lift/run data

### Phase 2: Data Classification
- Classifies captured resources as static metadata or dynamic status
- Uses regex pattern matching against OpenSkiMap reference data
- Calculates coverage percentages for lifts and runs

### Phase 3: Structure Analysis
- Generates schema overviews for each data source
- Extracts sample objects for analysis
- Identifies name, status, and identifier fields

### Phase 4: Cross-Source Mapping
- Maps relationships between static and dynamic data sources
- Establishes foreign key relationships using fuzzy matching
- Validates mappings against OpenSkiMap reference data

### Phase 5: Configuration Generation
- Uses LLM (OpenAI) to generate extraction configurations
- Supports JSON APIs, CSS selectors, and XPath
- Produces structured extraction selectors

### Phase 6: Iterative Refinement
- LangGraph-based agent for automated debugging
- Attempts up to 3 configuration refinements
- Success threshold: 20% coverage of lift/run status data

## Configuration

### Environment Variables

- `OPENAI_API_KEY` - Required for LLM-based config generation (Phase 5)

### Status Pages CSV

Configure resort status pages in `data/status_pages.csv`:

```csv
resort_id,resort_name,website_url,status_page_url
68b126bc...,Les Trois Vallées,https://www.les3vallees.com/,https://www.les3vallees.com/fr/live/...
```

## GitHub Actions

The project includes GitHub Actions workflows:

- **Get Ski Resort Data** (`.github/workflows/get_ski_resort_data.yml`)
  - Runs weekly on Sundays at midnight
  - Fetches latest OpenSkiMap data
  - Commits updated data files

- **CI** (`.github/workflows/ci.yml`)
  - Runs tests on push/pull request
  - Linting with Ruff
  - Type checking with mypy

- **Test Resort Configs** (`.github/workflows/test-configs.yml`)
  - Tests scraping configurations against live resort websites
  - Can test all resorts or a specific one by ID
  - Reports lift/run counts, status breakdown, and coverage vs OpenSkiMap
  - Updates the badge shown at the top of this README
  - Run manually or daily at 6 AM UTC

### Testing Configurations Locally

```bash
# Test all configured resorts
python scripts/test_configs.py

# Test a specific resort by ID
python scripts/test_configs.py --resort-id 68b126bc3175516c9263aed7635d14e37ff360dc

# Output JSON results
python scripts/test_configs.py --output results.json

# Quiet mode (summary only)
python scripts/test_configs.py --quiet
```

The test output includes:
- **Platform detection**: Identifies the backend system (Lumiplan, Skiplan, etc.)
- **Extraction method**: Describes how data is extracted (JSON API, HTML parsing, etc.)
- **Status counts**: Number of open/closed lifts and trails
- **Sample data**: First 3 lifts and trails with their details
- **Coverage**: Percentage of OpenSkiMap reference data found

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

## Testing

Run the test suite:

```bash
pytest tests/ -v
```

## License

MIT License - see LICENSE file for details.

## Data Source

Data is sourced from [OpenSkiMap](https://openskimap.org/), an open-source collaborative project for skiing and winter sports.
