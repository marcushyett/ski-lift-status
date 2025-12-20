# Dolomiti Superski Platform

## Overview

Dolomiti Superski is an Italian ski consortium covering multiple valleys in the Dolomites. Their websites use HTML tables for lift status.

## Data Source

Lift status is displayed in HTML tables on resort pages.

## HTML Structure

```html
<table>
  <tbody>
    <tr>
      <td>...</td>
      <td>Lift Name</td>
      <td>...</td>
      <td class="green">●</td>
    </tr>
  </tbody>
</table>
```

## Status Indicators

| Class | Status |
|-------|--------|
| `green` | open |
| `red` | closed |

## Implementation

See `extractDolomiti()` in runner.js.

The extractor:
1. Fetches the status page
2. Parses table rows
3. Extracts name from column 2
4. Checks column 4 class for status

## Known Resorts

| Resort | Coverage |
|--------|----------|
| Alta Badia | Dolomiti Superski |
| Val Gardena | Dolomiti Superski |

## Notes

- HTML structure may vary by resort within the network
- Some resorts may have different column layouts
- Consider using XHR fetcher to discover any hidden APIs
