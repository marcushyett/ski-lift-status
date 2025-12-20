# Infosnow Platform

## Overview

Infosnow is a Swiss ski resort information system. It provides HTML-based lift status pages.

## Data Source

```
http://www.infosnow.ch/~apgmontagne/?lang=en&pid={resort_id}&tab=web-wi
```

### Resort IDs

| Resort | PID |
|--------|-----|
| Verbier | 31 |

## HTML Structure

```html
<table>
  <tr>
    <td><img class="icon" src="status/{status}.png"></td>
    <td>Lift Name</td>
  </tr>
</table>
```

## Status Images

| Image Filename | Status |
|----------------|--------|
| `open.png`, `green.png` | open |
| `closed.png`, `red.png` | closed |

## Implementation

See `extractInfosnow()` in runner.js.

## Current Status

The Infosnow platform may have limited availability or inconsistent responses. Some Swiss resorts may have moved to different platforms.

## Notes

- HTTP (not HTTPS) endpoint
- May have SSL/TLS compatibility issues
- Consider alternative data sources for Swiss resorts
