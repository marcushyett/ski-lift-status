# Vail Resorts / Epic Platform

## Overview

Vail Resorts operates the Epic Pass network including major US resorts. They use a JavaScript-based TerrainStatusFeed system.

## Data Source

Lift status is embedded in JavaScript on terrain status pages:

```javascript
FR.TerrainStatusFeed = {
  Lifts: [
    { Name: "Lift Name", Status: 1 }
  ]
};
```

## Status Values

| Status Code | Meaning |
|-------------|---------|
| 0 | closed |
| 1 | open |
| 2 | hold |
| 3 | scheduled |

## Known Resorts

| Resort | URL Pattern |
|--------|------------|
| Vail | `/the-mountain/mountain-conditions/terrain-and-lift-status.aspx` |
| Beaver Creek | Same pattern |
| Park City | Same pattern |
| Whistler Blackcomb | Same pattern |
| Stowe | Same pattern |

## Current Status: BLOCKED

As of December 2024, Vail Resorts websites are **blocking automated requests** with:
- WAF (Web Application Firewall) challenges
- Akamai bot detection
- SSL/TLS restrictions

### Error Messages

```
403 Forbidden
"Access Denied"
"Request blocked by WAF"
```

## Workarounds Attempted

1. **User-Agent spoofing** - Not sufficient
2. **Different endpoints** - All blocked
3. **Mobile site** - Also blocked

## Alternative Data Sources

Consider:
- Official Vail Resorts mobile app APIs (requires reverse engineering)
- Third-party aggregators
- RSS feeds (if available)

## Implementation

See `extractVail()` in runner.js.

The extractor:
1. Fetches the terrain status page
2. Looks for `TerrainStatusFeed` in script tags
3. Parses the JavaScript object
4. Extracts lift names and status codes

## Notes

- This platform is inherited from the liftie project
- Implementation may need updating if Vail changes their frontend
- Consider monitoring for API changes or new endpoints
