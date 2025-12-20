# Debugging Guide: Finding Scraping Methods for Ski Resorts

This guide explains how to discover and implement data extraction for new ski resort websites.

## Core Principle

**Always prefer JSON APIs over HTML scraping.** Modern ski resort websites are typically Single Page Applications (SPAs) that load data dynamically. If a page displays lift status, there MUST be an API providing that data. Your job is to find it.

## Step 1: Initial Page Analysis

### Check the Network Tab

1. Open the resort's lift status page in Chrome/Firefox
2. Open DevTools (F12) → Network tab
3. Refresh the page
4. Filter by "XHR" or "Fetch"
5. Look for JSON responses containing lift/run data

Common API patterns:
- `/api/lifts`, `/api/facilities`, `/api/status`
- `?type=lift`, `?category=remontees`
- GraphQL endpoints (`/graphql`, `/__graphql`)

### Check Page Source

Look for embedded data in the HTML:

```bash
curl -s "https://example.com/lift-status" | grep -E "window\.__|\{\"lifts\"|REMONTEE|facilities"
```

Common patterns:
- `window.__NUXT__` - Nuxt.js apps
- `window.__NEXT_DATA__` - Next.js apps
- `window.__DATA__` or `window.initialData` - Custom SPAs
- `<script type="application/json">` - Embedded JSON

## Step 2: Using XHR Fetcher

For JavaScript-heavy pages that require rendering, use the XHR Fetcher service:

### Analyze Endpoint (Recommended First Step)

```bash
curl -s -X POST "$XHR_FETCH_URL/analyze" \
  -H "Authorization: Bearer $XHR_FETCH_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/lift-status", "timeout": 60000}'
```

The response includes:
- `primaryDataSource`: Type of data (json-api, graphql, nextjs-embedded, etc.)
- `detectedAPIs`: Array of discovered endpoints with URLs and sample data
- `pageMetadata`: Framework detection (React, Vue, Angular, etc.)

### Fetch Endpoint (Full Page Rendering)

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

Use `waitUntil: "networkidle"` for SPAs that load data after initial render.

## Step 3: Identifying Platform Types

### Known Platforms

Check if the resort uses a known platform:

| Indicator | Platform | Documentation |
|-----------|----------|---------------|
| `intermaps.com` in source | Intermaps | [intermaps.md](platforms/intermaps.md) |
| `lumiplan` in URLs | Lumiplan | [lumiplan.md](platforms/lumiplan.md) |
| `micadoweb` or `sgm.*.at` | Micado | [micado.md](platforms/micado.md) |
| `digisnow` or SKIPLAN XML | Skiplan | [skiplan.md](platforms/skiplan.md) |
| `TerrainStatusFeed` | Vail/Epic | [vail.md](platforms/vail.md) |
| `window.__NUXT__` | Nuxt.js | [nuxtjs.md](platforms/nuxtjs.md) |
| `window.__NEXT_DATA__` | Next.js | See below |
| `dolomitisuperski.com` | Dolomiti | [dolomiti.md](platforms/dolomiti.md) |

### Framework Detection

**Next.js Sites:**
```javascript
// Look for this in page source
<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{...}}}</script>
```

**Nuxt.js Sites:**
```javascript
// Look for this pattern
window.__NUXT__ = { state: { ... } }
// Or IIFE format
window.__NUXT__ = (function(a,b,c) { return {...} })(...);
```

**Vue.js (Generic):**
- Look for `v-` attributes, `data-v-` prefixes
- Check for Vue devtools hook: `__VUE__`

**React (Generic):**
- Look for `data-reactroot`, `__REACT_DEVTOOLS_GLOBAL_HOOK__`
- Often uses `window.__PRELOADED_STATE__` or similar

## Step 4: HTML Scraping (Last Resort)

Only use HTML scraping when no API is available. Server-rendered pages may require this approach.

### Common HTML Structures

**Tables:**
```javascript
const rows = doc.querySelectorAll('table.lifts tr');
rows.forEach(row => {
  const name = row.querySelector('td:nth-child(1)')?.textContent;
  const status = row.querySelector('td:nth-child(2)')?.textContent;
});
```

**List Items:**
```javascript
const items = doc.querySelectorAll('.lift-item, .facility-row');
items.forEach(item => {
  const name = item.querySelector('.name, .title, h3')?.textContent;
  const statusEl = item.querySelector('.status, .indicator, .state');
});
```

**Status Indicators:**

Look for status in:
- CSS classes: `.open`, `.closed`, `.status-open`, `.indicator.green`
- Image filenames: `open.png`, `green.svg`, `status_1.gif`
- Data attributes: `data-status="open"`, `data-state="1"`
- Text content: "Open", "Closed", "Ouvert", "Fermé"

### Status Normalization

Common status values and their meanings:

| Raw Value | Normalized |
|-----------|------------|
| `O`, `open`, `opened`, `1`, `true`, `green` | `open` |
| `F`, `closed`, `0`, `false`, `red` | `closed` |
| `P`, `scheduled`, `planned`, `expected` | `scheduled` |
| `A`, `avalanche` | `closed` (with note) |

Multilingual status:
- French: `ouvert` (open), `fermé` (closed), `prévu` (scheduled)
- German: `offen` (open), `geschlossen` (closed)
- Italian: `aperto` (open), `chiuso` (closed)

## Step 5: Finding the Right Page

### If the Given URL Doesn't Have Data

1. **Navigate to the official website** and look for:
   - "Lift Status", "Bergbahnen", "Remontées", "Impianti"
   - "Trail Map", "Conditions", "Snow Report"
   - "Live" or "Real-time" status pages

2. **Check for embedded iframes:**
   ```bash
   curl -s "https://example.com/conditions" | grep -i "iframe\|src="
   ```

   The iframe source may point to a data provider like Lumiplan or Intermaps.

3. **Check mobile app APIs:**
   - Sometimes the mobile app uses a cleaner API
   - Look for app download links and search for the app's API endpoints

4. **Check sitemap:**
   ```bash
   curl -s "https://example.com/sitemap.xml" | grep -i "lift\|status\|conditions"
   ```

### Common URL Patterns

| Language | Possible URLs |
|----------|---------------|
| English | `/lifts`, `/lift-status`, `/conditions`, `/terrain` |
| French | `/remontees`, `/etat-pistes`, `/domaine-skiable` |
| German | `/lifte`, `/bergbahnen`, `/anlagen`, `/pistenbericht` |
| Italian | `/impianti`, `/piste`, `/stato-piste` |

## Step 6: Testing and Validation

### Run the Extractor

```bash
cd /home/user/ski-lift-status/src/ski_lift_status/configs
node runner.js <resort-id>
```

### Check Output Quality

A working extractor should return:
- More than 2 lifts (unless it's a tiny resort)
- More than 2 runs (unless runs aren't tracked)
- Valid status values (open/closed/scheduled)
- Reasonable lift names (not HTML artifacts)

### Common Issues

**Empty Results:**
- API endpoint changed
- Data loads asynchronously (need XHR fetcher)
- Geo-blocking or WAF protection

**Wrong Data:**
- Parsing wrong element selectors
- Status mapping incorrect
- Summer season (lifts may show as closed)

**Partial Data:**
- Multiple data sources needed
- Pagination not handled
- Some facilities in different category

## Step 7: Implementation Checklist

When adding a new resort:

1. [ ] Identify the data source (API preferred)
2. [ ] Document the endpoint in CLAUDE.md if reusable
3. [ ] Add config to `resorts.json` with `dataUrl` if applicable
4. [ ] Implement extractor in `runner.js` if new platform
5. [ ] Test with `node runner.js <resort-id>`
6. [ ] Verify lift count meets minimum threshold (>2 lifts AND >2 runs)
7. [ ] Add platform documentation if new platform type

## Troubleshooting Specific Scenarios

### WAF/Bot Protection

Some sites block automated requests:
- Add realistic User-Agent headers
- Respect rate limits
- Consider if data is available elsewhere

### SSL/TLS Errors

Some older systems have certificate issues:
- Try HTTP instead of HTTPS
- Check if there's an alternative endpoint

### CORS Issues

If API returns CORS errors:
- The API is meant for browser-only access
- Look for a different endpoint or use XHR fetcher

### Empty JSON/No Lifts Showing

During off-season:
- Resorts may return empty arrays
- Check if there's a "winter" vs "summer" mode
- Look for `season=winter` parameters
