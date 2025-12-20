# Ski Resort Platform Documentation

This directory contains documentation for each ski resort platform/technology used to extract lift and run status data.

## Platform Categories

### Third-Party Data Providers

| Platform | Technology | Used By | Status |
|----------|------------|---------|--------|
| [Intermaps](intermaps.md) | JSON API | Austrian/German resorts | Active |
| [Lumiplan](lumiplan.md) | HTML/JSON | French resorts | Active |
| [Micado](micado.md) | JSON API | Austrian resorts | Active |
| [Skiplan](skiplan.md) | JSON/XML API | French resorts | Active |
| [Infosnow](infosnow.md) | HTML | Swiss resorts | Partial |

### Resort Network Platforms

| Platform | Technology | Used By | Status |
|----------|------------|---------|--------|
| [Vail/Epic](vail.md) | JS/JSON | US Vail resorts | Blocked |
| [SkiStar](skistar.md) | HTML/SimpleView | Scandinavian resorts | Active |
| [Dolomiti Superski](dolomiti.md) | HTML | Italian resorts | Active |

### Framework-Based

| Platform | Technology | Detection | Status |
|----------|------------|-----------|--------|
| [Nuxt.js](nuxtjs.md) | Embedded JSON | `window.__NUXT__` | Active |
| [Next.js](nextjs.md) | Embedded JSON | `__NEXT_DATA__` | Varies |

### Individual Resort Implementations

See [individual-resorts.md](individual-resorts.md) for resorts with custom implementations.

## Quick Reference

To add a new resort:

1. Use the [debugging guide](../debugging-guide.md) to identify the data source
2. Check if it matches an existing platform
3. Add to `resorts.json` with appropriate platform type
4. Test with `node runner.js <resort-id>`
