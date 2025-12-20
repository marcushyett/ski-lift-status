# Individual Resort Implementations

This document covers resorts with custom implementations that don't fit into a standard platform category.

## Laax (Switzerland)

**Platform:** `laax`

**Data Source:** Server-rendered HTML at `https://live.laax.com/de/anlagen`

**HTML Structure:**
```html
<div class="widget lift">
  <div class="indicator open"></div>
  <div class="h3">Lift Name</div>
</div>
```

**Status Classes:**
- `indicator open` - open
- `indicator closed` - closed
- `indicator in-preparation` - scheduled

---

## Swiss Resorts (Infosnow)

**Platform:** `infosnow`

Used by some Swiss resorts via the Infosnow system.

**Data Source:** `http://www.infosnow.ch/~apgmontagne/?lang=en&pid={id}&tab=web-wi`

**HTML Structure:**
```html
<table>
  <tr>
    <td><img class="icon" src="status/open.png"></td>
    <td>Lift Name</td>
  </tr>
</table>
```

---

## Davos/Parsenn (Switzerland)

**Platform:** `davos`

**Issue:** Uses Vue.js SPA that loads data dynamically.

**Workaround:** Look for embedded JSON in script tags or identify API endpoints.

---

## Arosa Lenzerheide (Switzerland)

**Platform:** `arosa`

Similar to Davos - Vue.js SPA requiring API discovery.

---

## St. Moritz/Corviglia (Switzerland)

**Platform:** `stmoritz`

**Data Source:** HTML tables on status pages.

---

## GrandValira (Andorra)

**Platform:** `grandvalira`

**Technology:** Drupal CMS with embedded JSON data.

---

## Livigno (Italy)

**Platform:** `livigno`

**Data Source:** HTML tables/lists with lift status.

---

## Baqueira (Spain)

**Platform:** `baqueira`

**Data Source:** HTML tables with status images.

---

## Perisher (Australia)

**Platform:** `perisher`

**Data Source:** HTML lift status page.

---

## Big Sky (USA)

**Platform:** `bigsky`

**Data Source:** Embedded JSON in script tags.

**Issue:** May require JavaScript execution for full data.

---

## Deer Valley (USA)

**Platform:** `deervalley`

**Data Source:** Embedded JSON or HTML tables.

---

## Adding New Custom Resorts

1. Analyze the page structure using browser DevTools
2. Check for embedded JSON (`window.__DATA__`, `__NUXT__`, etc.)
3. Look for API calls in Network tab
4. Create extractor function in runner.js
5. Add to platform switch statement
6. Test with `node runner.js <resort-id>`
