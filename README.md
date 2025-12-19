# Ski Lift Status

![Resort Configs](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/marcushyett/ski-lift-status/main/.github/badges/config-status.json)
[![CI](https://github.com/marcushyett/ski-lift-status/actions/workflows/ci.yml/badge.svg)](https://github.com/marcushyett/ski-lift-status/actions/workflows/ci.yml)

**A real-time ski resort lift and run status API** that maps live status data to [OpenSkiMap](https://openskimap.org/) resort identifiers.

Access any ski resort's live lift and run status through a unified API, with data mapped to OpenSkiMap IDs for seamless integration with ski mapping applications.

## How It Works

1. **Status Page Discovery** - Automatically finds official lift status pages for resorts using AI-powered search
2. **Data Extraction** - Scrapes real-time lift/run status from resort websites (supports Lumiplan, Skiplan, and other platforms)
3. **OpenSkiMap Mapping** - Maps extracted data to OpenSkiMap resort, lift, and run IDs

## Quick Start

```bash
pip install -r requirements.txt

# Test fetching live status for configured resorts
python scripts/test_configs.py
```

## API Usage

```python
import asyncio
from ski_lift_status import load_resorts, get_lifts_for_resort

# Get OpenSkiMap data
resorts = load_resorts()
resort_lifts = get_lifts_for_resort("68b126bc3175516c9263aed7635d14e37ff360dc")

# Fetch live status (example with configured resort)
from ski_lift_status.scraping import run_pipeline_for_resort

result = asyncio.run(run_pipeline_for_resort(
    resort_id="68b126bc3175516c9263aed7635d14e37ff360dc",
    status_page_url="https://www.les3vallees.com/fr/live/ouverture-des-pistes-et-remontees",
    resort_name="Les Trois Vallées",
))

if result.success:
    for lift in result.lifts_data:
        print(f"{lift['name']}: {lift['status']}")
```

## GitHub Actions

| Workflow | Description |
|----------|-------------|
| **Discover Status Pages** | Finds resort status pages using Serper.dev search |
| **Test Resort Configs** | Validates live status extraction daily |
| **Get Ski Resort Data** | Fetches latest OpenSkiMap data weekly |

## Credits & Data Sources

This project is built on top of amazing open-source work:

- **[OpenSkiMap](https://openskimap.org/)** - Open-source ski map providing comprehensive resort, lift, and run data. All resort/lift/run IDs and reference data come from OpenSkiMap.

- **[Liftie](https://liftie.info/)** - Inspiration for providing unified ski lift status data. Liftie pioneered the concept of aggregating lift status across resorts.

## License

MIT License - see LICENSE file for details.
