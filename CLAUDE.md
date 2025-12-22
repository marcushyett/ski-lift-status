# Ski Resort Status - Development Notes

## Project Overview

This is an npm module for fetching live ski resort lift and run status data, with OpenSkiMap integration for standardized identification of lifts and runs across platforms.

## Architecture

### Module Structure

```
lib/
├── fetchers/
│   ├── base.js              # Base fetcher interface
│   └── lumiplan/            # Lumiplan platform implementation
│       ├── index.js         # Main Lumiplan fetcher class
│       ├── api.js           # Lumiplan API client
│       └── matcher.js       # OpenSkiMap matching logic
├── resorts.js               # Resort registry
└── index.js                 # Main module entry point
```

### Design Principles

- **Platform-based fetchers**: Each ski resort data platform (Lumiplan, etc.) has its own fetcher implementation
- **Direct API access**: Prefer stable JSON API endpoints over HTML scraping or browser automation
- **OpenSkiMap integration**: Match lift/run names to OpenSkiMap IDs for standardized identification
- **Fuzzy matching**: Handle name variations and duplicates using Levenshtein distance and type/difficulty hints

### Adding New Resorts

1. **Find the platform**: Determine which data platform the resort uses (e.g., Lumiplan, Skiplan, etc.)
2. **Add to registry**: Add resort config to `lib/resorts.js` with:
   - `id`: Unique identifier (e.g., 'les-trois-vallees')
   - `name`: Display name
   - `openskimap_id`: OpenSkiMap resort ID (40-char hex string)
   - `platform`: Platform identifier
   - Platform-specific fields (e.g., `lumiplanMapId` for Lumiplan resorts)

### Adding New Platforms

1. **Create fetcher directory**: `lib/fetchers/<platform>/`
2. **Implement fetcher class**: Extend `BaseFetcher` from `lib/fetchers/base.js`
3. **Required methods**:
   - `async fetch()`: Return `{ resort, lifts, runs }`
   - `static getMetadata()`: Return platform metadata
4. **Register fetcher**: Add to `FETCHERS` map in `lib/index.js`

## XHR Fetcher Tool (API Discovery)

For discovering API endpoints on JavaScript-heavy resort websites, use the XHR Fetcher service to intercept network requests and reveal underlying APIs.

**Environment Variables:**
- `XHR_FETCH_URL` - Base URL for the xhr-fetcher service
- `XHR_FETCH_KEY` - API key for authentication

### Analyze endpoint (discover APIs)
```bash
curl -s -X POST "$XHR_FETCH_URL/analyze" \
  -H "Authorization: Bearer $XHR_FETCH_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/lift-status", "timeout": 60000}'
```

Response includes:
- `primaryDataSource` - Type of data source (json-api, graphql, nextjs-embedded, etc.)
- `detectedAPIs` - Array of discovered API endpoints with:
  - `url` - The actual API URL
  - `schema` - JSON schema of the response
  - `sample` - Sample response data

### Fetch endpoint (get full page data)
```bash
curl -s -X POST "$XHR_FETCH_URL/fetch" \
  -H "Authorization: Bearer $XHR_FETCH_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "waitUntil": "networkidle",
    "timeout": 60000
  }'
```

Parameters:
- `url` (required): Target URL
- `waitUntil`: Navigation trigger (`load`, `domcontentloaded`, `networkidle`)
- `timeout`: Max wait time (default: 60s, max: 360s)
- `waitForSelector`: CSS selector to wait for
- `additionalWaitMs`: Extra delay after loading

Documentation: https://github.com/marcushyett/xhr-fetcher

## OpenSkiMap Data

The repository includes OpenSkiMap reference data for matching:

- `data/lifts.csv` - OpenSkiMap lift reference data
- `data/runs.csv` - OpenSkiMap run reference data

This data is fetched automatically via GitHub Actions workflow.

### Duplicate Names

OpenSkiMap data contains duplicate lift/run names within resorts. The matching logic handles this by:

1. **Fuzzy name matching**: Using Levenshtein distance to find all entities with similar names
2. **Type/difficulty hints**: Using lift type or run difficulty to disambiguate between duplicates
3. **Multiple IDs**: Returning arrays of all matching OpenSkiMap IDs when exact disambiguation isn't possible

### Type Normalization

Lift types are normalized from platform-specific values to OpenSkiMap standard types:

- `GONDOLA` → `gondola`
- `CHAIRLIFT`, `DETACHABLE_CHAIRLIFT` → `chair_lift`
- `SURFACE_LIFT`, `DRAG_LIFT` → `platter`
- etc.

### Difficulty Normalization

Run difficulties are normalized from platform-specific levels to OpenSkiMap standard difficulties:

- `GREEN` → `novice`
- `BLUE` → `easy`
- `RED` → `intermediate`
- `BLACK` → `advanced`
- `ORANGE`, `YELLOW` → `expert`, `extreme`

## Testing

Run the test script to verify functionality:

```bash
npm test
```

This tests fetching data for Les Trois Vallées and displays summary statistics.
