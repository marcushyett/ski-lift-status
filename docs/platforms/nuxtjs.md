# Nuxt.js Sites

## Overview

Nuxt.js is a Vue.js framework that often embeds initial state data in the HTML. Ski resort sites built with Nuxt.js can be scraped by extracting this embedded data.

## Detection

Look for:
- `window.__NUXT__` in page source
- Vue.js indicators (`v-`, `data-v-`)
- `_nuxt/` in asset URLs

## Data Formats

### Simple Object Format

```html
<script>window.__NUXT__ = { state: { ... } };</script>
```

### IIFE Format

```html
<script>window.__NUXT__ = (function(a,b,c) { return {...} })(val1, val2, val3);</script>
```

## Extraction

The `extractNuxtData()` function handles multiple Nuxt formats:

1. Parses script tags containing `window.__NUXT__`
2. Executes the JavaScript in a sandboxed VM
3. Returns the parsed data object

## Data Paths

Common data paths in Nuxt ski resort sites:

```javascript
// Cervinia/Italian resorts
$.state.impianti.SECTEUR[*].REMONTEE[*]
$.state.impianti.SECTEUR[*].PISTE[*]

// Item structure
{
  "@attributes": {
    "nom": "Lift Name",
    "etat": "O"
  }
}
```

## Configuration

```json
{
  "platform": "nuxt",
  "url": "https://example.com/lifts",
  "config": {
    "lifts": "$.state.impianti.SECTEUR[*].REMONTEE[*]",
    "runs": "$.state.impianti.SECTEUR[*].PISTE[*]",
    "name": "@attributes.nom",
    "status": "@attributes.etat",
    "statusMap": {
      "O": "open",
      "A": "open",
      "F": "closed",
      "P": "scheduled"
    }
  }
}
```

## Implementation

See `extractNuxt()` in runner.js.

## Known Resorts

| Resort | Data Path |
|--------|-----------|
| Cervinia | `state.impianti.SECTEUR[*].REMONTEE[*]` |

## Troubleshooting

1. **IIFE not parsing**: Check for complex JavaScript that may need additional handling
2. **Empty data**: The state may load asynchronously - may need XHR fetcher
3. **Different structure**: Each Nuxt site may have unique data paths
