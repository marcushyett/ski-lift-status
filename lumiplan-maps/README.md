# Lumiplan Ski Data

A Node.js module for fetching real-time ski resort lift and run data from Lumiplan interactive maps, with fuzzy matching to OpenSkiMap IDs.

## Installation

```bash
npm install
```

## Quick Start

```javascript
import { getSkiAreaData, getAvailableMaps } from 'lumiplan-ski-data';

// List available maps
console.log(getAvailableMaps());

// Get full data for a ski area
const data = await getSkiAreaData('tignes-valdisere');
console.log(data.lifts);  // Array of lifts with real-time status
console.log(data.runs);   // Array of runs with real-time status

// Get just lift status summary
const liftStatus = await getLiftStatus('paradiski');
console.log(`${liftStatus.open}/${liftStatus.total} lifts open`);
```

## Available Maps

| ID | Name | Resorts |
|----|------|---------|
| `tignes-valdisere` | Espace Killy | Tignes, Val d'Isère |
| `paradiski` | Paradiski | Les Arcs, La Plagne, Peisey-Vallandry |
| `les-3-vallees` | Les 3 Vallées | Courchevel, Méribel, Val Thorens, Les Menuires, Orelle |
| `aussois` | Aussois | Aussois |
| `orcieres` | Orcières | Orcières Merlette 1850 |
| `vaujany` | Alpe d'Huez Grand Domaine | Vaujany, Oz, Alpe d'Huez |

## API

### `getSkiAreaData(mapId, options?)`

Fetches complete lift and run data for a ski area.

**Parameters:**
- `mapId` - One of the available map IDs
- `options.lang` - Language code (default: 'en')
- `options.matchOsm` - Whether to match with OpenSkiMap IDs (default: true)

**Returns:**
```javascript
{
  lifts: [{
    id: 5226,
    name: 'TK DE COMBE FOLLE',
    type: 'drag_lift',
    status: 'open',
    operating: true,
    capacity: 1,
    duration: 4,
    length: 869,
    osmMatch: { osmId: '...', osmName: '...', confidence: 'high' }
  }, ...],
  runs: [{
    id: 5483,
    name: 'COL MADELEINE',
    type: 'downhill_skiing',
    difficulty: 'easy',
    status: 'scheduled',
    groomingStatus: 'GROOMED',
    snowQuality: 'HARD_PACKED',
    length: 982,
    osmMatch: { osmId: '...', osmName: '...', confidence: 'medium' }
  }, ...],
  resorts: [...],
  metadata: {
    fetchedAt: '2024-01-15T10:30:00.000Z',
    language: 'en',
    mapId: 'tignes-valdisere',
    displayName: 'Tignes - Val d\'Isère (Espace Killy)'
  }
}
```

### `getLiftStatus(mapId)`

Get a summary of lift status.

### `getRunStatus(mapId)`

Get a summary of run status.

### `getAvailableMaps()`

Get list of available map configurations.

## CLI

```bash
# Show available maps
node src/cli.js --help

# Get data for a resort
node src/cli.js tignes-valdisere

# Get summary only
node src/cli.js paradiski --summary

# Output as JSON
node src/cli.js les-3-vallees --json
```

## Generating OpenSkiMap Data

To enable OpenSkiMap ID matching, generate the data files:

```bash
node src/generate-osm-data.js
```

This reads from the parent `ski-lift-status/data/*.csv` files and creates JSON files in `data/`.

## License

MIT
