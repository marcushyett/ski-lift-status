# Lumiplan Platform

## Overview

Lumiplan is a French company providing ski resort information systems. They offer two main data sources:

1. **HTML Bulletin** - Traditional web pages with lift/run status
2. **JSON API** - Interactive map services API (newer)

## Bulletin HTML (Legacy)

### Endpoint

```
https://bulletin.lumiplan.pro/bulletin.php?station={station_name}&region=alpes&pays=france&lang=en
```

### Station Names

| Resort | Station Name |
|--------|-------------|
| La Plagne | `la-plagne` |
| Méribel | `alpina-mottaret` |
| Courchevel | `courchevel` |
| Val Thorens | `les3vallees` |

### HTML Formats

#### New Format (POI_info)

Used by resorts like La Plagne:

```html
<div class="POI_info">
  <span class="nom">Lift Name</span>
  <img class="img_type" src="image/TC.svg">
  <img class="img_status" src="image/lp_runway_trail_opened.svg">
</div>
```

#### Old Format (prl_group)

Used by 3 Vallées resorts:

```html
<div class="prl_group" title="Lift Name">
  <img class="img_type" src="...">
  <img class="image_status" src="etats/O.svg">
</div>
```

### Status Images

| Image | Status |
|-------|--------|
| `_opened` / `_open` | open |
| `_scheduled` | scheduled |
| `_closed` | closed |
| `etats/O.svg` | open |
| `etats/P.svg` | scheduled |
| `etats/F.svg` or `H.svg` | closed |

### Variant: Summary Format

Some resorts (e.g., Serre-Chevalier) show only summary statistics (e.g., "12/20 lifts open") without individual lift names. These require the JSON API or alternative data sources.

## JSON API (lumiplanMapId)

### Endpoints

```
https://lumiplay.link/interactive-map-services/public/map/{mapId}/staticPoiData?lang=en
https://lumiplay.link/interactive-map-services/public/map/{mapId}/dynamicPoiData?lang=en
```

### Map IDs

| Resort | Map ID |
|--------|--------|
| (example) | `09110215-8a54-42cd-991a-1c534bfb5115` |

### Response Structure

**staticPoiData:**
```json
{
  "items": [
    {
      "data": {
        "id": "123",
        "name": "Lift Name",
        "type": "LIFT",
        "liftType": "GONDOLA"
      }
    }
  ]
}
```

**dynamicPoiData:**
```json
{
  "items": [
    {
      "id": "123",
      "openingStatus": "OPEN"
    }
  ]
}
```

### Status Values

| API Status | Normalized |
|------------|------------|
| `OPEN` | open |
| `FORECAST` | scheduled |
| `DELAYED` | scheduled |
| `CLOSED` | closed |
| `OUT_OF_PERIOD` | closed |

## Configuration

In `resorts.json`:

```json
{
  "platform": "lumiplan",
  "dataUrl": "https://bulletin.lumiplan.pro/bulletin.php?station=...",
  "lumiplanMapId": "optional-map-id-for-json-api"
}
```

If `lumiplanMapId` is provided, the JSON API is used. Otherwise, HTML parsing is attempted.

## Troubleshooting

1. **Empty results**: Check if the station name is correct
2. **Only summary data**: Resort may use new format without individual items
3. **Different HTML structure**: May need to find the correct station name (some resorts have multiple)
