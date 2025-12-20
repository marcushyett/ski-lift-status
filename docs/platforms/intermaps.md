# Intermaps Platform

## Overview

Intermaps is a mapping and data platform used by many Austrian and German ski resorts. It provides a JSON API with lift and slope status data.

## API Endpoint

```
https://winter.intermaps.com/{resort_id}/data?lang=en
```

### Resort IDs

| Resort | Intermaps ID |
|--------|-------------|
| Sölden | `soelden` |
| Ischgl | `silvretta_arena` |
| Saalbach Hinterglemm Leogang Fieberbrunn | `saalbach_hinterglemm_leogang_fieberbrunn` |
| Mayrhofen | `mayrhofen` |
| Zillertal Arena | `zillertal_arena` |

## Response Structure

```json
{
  "lifts": [
    {
      "popup": {
        "title": "Lift Name",
        "desc": "yes",
        "lynx-type": "lift",
        "subtitle": "6-chair lift",
        "additional-info": {
          "length": 1750,
          "capacity": 2450,
          "altitude-valley": 1348,
          "altitude-mountain": 1920
        }
      },
      "status": "open",
      "id": "L_59413"
    }
  ],
  "slopes": [
    {
      "popup": {
        "title": "Run Name",
        "subtitle": "red"
      },
      "status": "open",
      "id": "P_12345"
    }
  ]
}
```

## Status Values

| API Status | Normalized |
|------------|------------|
| `open` | open |
| `closed` | closed |
| `scheduled` | scheduled |

## Detection

Look for:
- `intermaps.com` in embedded iframes or data sources
- `data-src="https://winter.intermaps.com/{id}"` attributes
- References to "Intermaps" in page source

## Implementation

See `extractSoelden()`, `extractIschgl()`, `extractSaalbach()` in runner.js.

All use the same API structure, differing only in the resort ID.

## Notes

- The API provides both lifts and slopes (runs)
- Lift types are in `popup.subtitle` (e.g., "6-chair lift", "cable car", "T-bar")
- Additional metadata includes altitude and capacity
- Language parameter (`lang=en`) provides English names
