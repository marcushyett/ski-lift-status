# Ski Resort Status Configs

JSON-based config system for extracting lift and run status from ski resort websites, with automatic OpenSkiMap name mapping.

## Inspired by Liftie

This config system is inspired by [liftie](https://github.com/pirxpilot/liftie), an excellent open-source ski lift status aggregator. If you're looking for a production-ready lift status service with 190+ resorts, check out liftie at [liftie.info](https://liftie.info/).

**Key difference from liftie:** This system maps extracted data to OpenSkiMap IDs, enabling integration with ski mapping applications.

## Quick Start

```bash
# List available resorts
node runner.js

# Extract status for a resort
node runner.js courchevel

# Extract with OpenSkiMap mapping
node runner.js courchevel --map

# Extract all resorts
node runner.js --all
```

## Config Structure

Resorts are configured in `resorts.json`:

```json
{
  "id": "resort-slug",
  "name": "Resort Name",
  "openskimap_id": "68b126bc3175516c9263aed7635d14e37ff360dc",
  "platform": "lumiplan",
  "url": "https://resort.com/lifts",
  "dataUrl": "https://api.resort.com/status",
  "liftieId": "resort-id-in-liftie"
}
```

## Supported Platforms

| Platform | Description | Resorts |
|----------|-------------|---------|
| `lumiplan` | Lumiplan bulletin system | 14 French resorts |
| `skiplan` | Skiplan JSON API | La Plagne, Les Arcs, Les Sybelles |
| `dolomiti` | Dolomiti Superski | Alta Badia, Cortina, Val Gardena |
| `nuxt` | Nuxt.js __NUXT__ data | Zermatt-Cervinia |
| `vail` | Vail Resorts Epic Pass | Breckenridge |
| `infosnow` | Swiss Infosnow APGSGA | Verbier |
| `skiwelt` | SkiWelt data-state | SkiWelt |
| `kitzski` | Kitzbühel pattern | KitzSki |
| `serfaus` | Serfaus pattern | Serfaus-Fiss-Ladis |
| `custom` | Needs implementation | 7 resorts |

## OpenSkiMap Integration

The `name_mapper.js` module provides automatic mapping of extracted lift/run names to OpenSkiMap IDs:

```javascript
const { mapResortToOpenSkiMap } = require('./name_mapper.js');

const extracted = { lifts: [{ name: 'Cascades', status: 'open' }], runs: [] };
const result = mapResortToOpenSkiMap('68b126bc...', extracted);

console.log(result.lifts.mapped);
// [{ online_name: 'Cascades', openskimap_id: '11effb19...', match_type: 'exact', status: 'open' }]
```

Mapping types:
- `exact` - Exact string match (100% confidence)
- `normalized` - Match after accent/case normalization (90% confidence)
- `fuzzy` - Fuzzy string matching (75-99% confidence)

## Files

- `resorts.json` - Master config with all resort definitions
- `runner.js` - Node.js extractor that runs configs
- `name_mapper.js` - OpenSkiMap name mapping module
- `platforms/` - Platform-specific extractor definitions (reference)

## Adding a New Resort

1. Identify the platform used by the resort website
2. Find the resort's OpenSkiMap ID
3. Add entry to `resorts.json`
4. Test extraction: `node runner.js new-resort --map`
5. Verify name mapping coverage
