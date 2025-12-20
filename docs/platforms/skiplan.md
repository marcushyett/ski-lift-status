# Skiplan Platform

## Overview

Skiplan (also known as SKIPLAN) is a French ski resort management system. It provides data in both JSON and XML formats.

## Variants

### SKIPLAN XML (skiplanxml)

Used by resorts that expose the raw SKIPLAN XML data, often through WordPress API endpoints.

#### Endpoint Example

```
https://backoffice.avoriaz.com/wp-json/api/avoriaz/get_digisnow
```

#### Response Structure

```xml
<REMONTEE nom="Lift Name" etat="O"/>
<PISTE nom="Run Name" etat="F"/>
```

#### Status Codes

| Code | Status |
|------|--------|
| `O` | open (ouvert) |
| `P` | scheduled (prévu) |
| `F` | closed (fermé) |

### Skiplan JSON (skiplan)

Used by resorts with JSON API endpoints.

#### Response Structure

```json
{
  "remontees": [
    {
      "nom": "Lift Name",
      "etat": "O"
    }
  ],
  "pistes": [
    {
      "nom": "Run Name",
      "etat": "F"
    }
  ]
}
```

Alternative field names:
- `nom` / `name` / `libelle`
- `etat` / `status` / `ouverture`

## Detection

Look for:
- `digisnow` in API URLs
- SKIPLAN XML format in responses
- WordPress JSON API patterns (`/wp-json/api/`)

## Configuration

```json
{
  "platform": "skiplanxml",
  "dataUrl": "https://backoffice.example.com/wp-json/api/resort/get_digisnow"
}
```

## Implementation

See `extractSkiplanXml()` and `extractSkiplan()` in runner.js.

## Known Resorts

| Resort | Format |
|--------|--------|
| Avoriaz | SKIPLAN XML |

## Notes

- XML attributes may be escaped with backslashes (`\"`)
- Entity encoding may need handling (`&apos;`, `&amp;`)
- The digisnow endpoint is typically exposed via WordPress REST API
