# SkiStar Platform

## Overview

SkiStar operates ski resorts primarily in Sweden and Norway. They use a React-based SPA with SimpleView components.

## Data Source

SkiStar pages load lift data via SimpleView URLs embedded in data attributes.

## Detection

Look for:
- `data-url*="SimpleView"` attributes
- `lpv-list__item` class elements
- SkiStar branding/domains

## HTML Structure

```html
<div data-url="/api/path/SimpleView?param=value">...</div>

<!-- After fetch -->
<div class="lpv-list__item">
  <span class="lpv-list__item-name">Lift Name</span>
  <span class="lpv-list__item-status lpv-list__item-status--is-open">Open</span>
</div>
```

## Status Classes

| Class | Status |
|-------|--------|
| `lpv-list__item-status--is-open` | open |
| (default) | closed |

## Implementation

See `extractSkistar()` in runner.js.

The extractor:
1. Fetches main page
2. Finds SimpleView URLs in data attributes
3. Fetches each SimpleView content
4. Parses lift items from the response

## Known Resorts

| Resort | Country |
|--------|---------|
| Åre | Sweden |
| Trysil | Norway |
| Sälen | Sweden |
| Hemsedal | Norway |

## Notes

- Multiple SimpleView requests may be needed
- React hydration may affect initial HTML
- Consider XHR fetcher for discovering API endpoints
