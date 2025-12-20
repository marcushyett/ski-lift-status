# Micado Platform

## Overview

Micado provides ski resort management software used by Austrian resorts. The platform offers a JSON API through the SkigebieteManager (SGM) system.

## API Endpoints

### SkiWelt Format

```
https://www.skiwelt.at/webapi/micadoweb?api=Micado.Ski.Web/Micado.Ski.Web.IO.Api.FacilityApi/List.api&client=https%3A%2F%2Fsgm.skiwelt.at&lang=en&region=skiwelt&season=winter&typeIDs=1
```

### KitzSki Format

```
https://www.kitzski.at/webapi/micadoweb?api=SkigebieteManager/Micado.SkigebieteManager.Plugin.FacilityApi/ListFacilities.api&extensions=o&client=https%3A%2F%2Fsgm.kitzski.at&lang=en&region=kitzski&season=winter&type=lift
```

## Response Structure

### SkiWelt Response

```json
{
  "items": [
    {
      "title": "Lift Name",
      "state": "opened"
    }
  ]
}
```

### KitzSki Response

```json
{
  "facilities": [
    {
      "title": "Lift Name",
      "status": 1
    }
  ]
}
```

## Status Values

### SkiWelt

| API State | Normalized |
|-----------|------------|
| `opened` | open |
| `open` | open |
| `scheduled` | scheduled |
| (other) | closed |

### KitzSki

| API Status | Normalized |
|------------|------------|
| `1` | open |
| `0` | closed |

## Detection

Look for:
- `webapi/micadoweb` in network requests
- `sgm.*.at` domains in iframes or scripts
- "Micado" or "SkigebieteManager" in source

## Implementation

See `extractSkiwelt()` and `extractKitzski()` in runner.js.

## Known Resorts

| Resort | Platform Variant |
|--------|-----------------|
| SkiWelt | skiwelt |
| KitzSki (Kitzbühel) | kitzski |

## Notes

- API parameters differ between resort implementations
- `typeIDs=1` typically filters for lifts
- The `client` parameter specifies the SGM instance
- Both summer and winter seasons are supported via `season` parameter
