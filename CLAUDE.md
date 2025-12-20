# Ski Lift Status - Development Notes

## Architecture Principles

### Runner.js Extraction Design
The `runner.js` file performs all resort data extraction using **direct HTTP requests only**:
- NO browser rendering or JavaScript execution (except jsdom for HTML parsing as last resort)
- Prefer stable JSON API endpoints over HTML scraping
- Each resort config should specify a `dataUrl` pointing to a JSON API when available
- HTML parsing should be a fallback, not the primary method

### Why This Matters
- JSON APIs are more stable than HTML structure (less likely to break on site redesigns)
- Direct HTTP is faster and more reliable than browser automation
- Configs are easier to maintain and debug with clean API endpoints

## CRITICAL RULE: Never Give Up on a Resort

**There is no such thing as "requires JavaScript rendering".** Every JavaScript-heavy page loads its data from an API - you just need to discover it.

When a resort page appears to require JavaScript:
1. **ALWAYS use the XHR Fetcher `/analyze` endpoint** to discover the underlying APIs
2. **Extract the JSON API URL** from the detected APIs
3. **Configure the resort** to call that API directly
4. **NEVER mark a resort as "requiresBrowserRendering"** or give up

Every modern ski resort website loads lift/run data from a backend API. The XHR Fetcher tool intercepts these API calls and reveals them. Use it!

## XHR Fetcher Tool (For Discovery/Debugging Only)

**IMPORTANT**: The XHR Fetcher is a development tool for discovering API endpoints. It should NOT be used in runner.js - it's only for building configs and debugging sites.

For pages that use JavaScript to load data dynamically, use the XHR Fetcher service to discover API endpoints:

**Environment Variables:**
- `XHR_FETCH_URL` - The base URL for the xhr-fetcher service
- `XHR_FETCH_KEY` - API key for authentication

**Usage:**

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

## Discovered API Endpoints

### SkiWelt (skiwelt platform)
```
https://www.skiwelt.at/webapi/micadoweb?api=Micado.Ski.Web/Micado.Ski.Web.IO.Api.FacilityApi/List.api&client=https%3A%2F%2Fsgm.skiwelt.at&lang=en&region=skiwelt&season=winter&typeIDs=1
```
Response: `items[].title`, `items[].state` ("opened"/"closed")

### KitzSki (kitzski platform)
```
https://www.kitzski.at/webapi/micadoweb?api=SkigebieteManager/Micado.SkigebieteManager.Plugin.FacilityApi/ListFacilities.api&extensions=o&client=https%3A%2F%2Fsgm.kitzski.at&lang=en&region=kitzski&season=winter&type=lift
```
Response: `facilities[].title`, `facilities[].status` (1=open, 0=closed)

### Sölden (soelden/intermaps platform)
```
https://winter.intermaps.com/soelden/data?lang=en
```
Response: `lifts[].popup.title`, `lifts[].status` ("open"/"closed"), `slopes[].popup.title`, `slopes[].status`

## Project Structure

- `src/ski_lift_status/configs/runner.js` - Main extraction logic
- `src/ski_lift_status/configs/resorts/` - Individual resort config files (one JSON per resort)
- `src/ski_lift_status/configs/resorts/index.js` - Loads all resort configs dynamically
- `data/lifts.csv` - OpenSkiMap lift reference data
- `data/runs.csv` - OpenSkiMap run reference data

## Testing a specific resort
```bash
cd /home/user/ski-lift-status/src/ski_lift_status/configs
node runner.js <resort-id>
```
