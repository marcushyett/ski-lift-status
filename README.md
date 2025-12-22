# Ski Resort Status

**A real-time ski resort lift and run status library** that fetches live data from ski resorts and maps it to [OpenSkiMap](https://openskimap.org/) identifiers.

Access ski resort live lift and run status through a simple API, with data automatically matched to OpenSkiMap IDs for seamless integration with ski mapping applications.

## Features

- **TypeScript-first**: Full type safety with TypeScript and Zod schema validation
- Fetch live lift and run status data from ski resorts
- Automatic matching to OpenSkiMap IDs for standardized lift/run identification
- Support for multiple ski resort data platforms
- Comprehensive metadata: opening times, capacity, altitude, grooming status, snow quality
- Handles duplicate lift/run names with intelligent type-based disambiguation
- **Schema validation**: Runtime validation with Zod ensures data consistency across platforms
- Minimal dependencies - only Zod for validation

## Installation

```bash
npm install ski-resort-status
```

Or using the local module:

```bash
npm install /path/to/ski-lift-status
```

## Quick Start

### JavaScript

```javascript
const { fetchResortStatus, getSupportedResorts } = require('ski-resort-status');
```

### TypeScript

```typescript
import { fetchResortStatus, getSupportedResorts, type ResortStatus, type Lift, type Run } from 'ski-resort-status';

// List all supported resorts
const resorts = getSupportedResorts();
console.log(resorts);
// [
//   { id: 'les-trois-vallees', name: 'Les Trois Vallées', openskimap_id: '68b...', platform: 'lumiplan' },
//   ...
// ]

// Fetch live data for a resort
const data = await fetchResortStatus('les-trois-vallees');
console.log(`${data.resort.name}: ${data.lifts.length} lifts, ${data.runs.length} runs`);

// Lifts array
data.lifts.forEach(lift => {
  console.log(`${lift.name}: ${lift.status}`);
  console.log(`  Type: ${lift.liftType}`);
  console.log(`  OpenSkiMap IDs: ${lift.openskimap_ids.join(', ')}`);
  console.log(`  Capacity: ${lift.capacity} persons/hour`);
});

// Runs array
data.runs.forEach(run => {
  console.log(`${run.name}: ${run.status}`);
  console.log(`  Level: ${run.level}`);
  console.log(`  OpenSkiMap IDs: ${run.openskimap_ids.join(', ')}`);
  console.log(`  Grooming: ${run.groomingStatus}`);
});
```

## API Reference

### `fetchResortStatus(resortIdOrOsmId)`

Fetch live status data for a resort.

**Parameters:**
- `resortIdOrOsmId` (string): Resort ID (e.g., 'les-trois-vallees') or OpenSkiMap resort ID (40-char hex string)

**Returns:** Promise resolving to:
```javascript
{
  resort: {
    id: string,           // Resort ID
    name: string,         // Resort name
    openskimap_id: string // OpenSkiMap resort ID
  },
  lifts: [
    {
      name: string,              // Lift name
      status: string,            // 'open', 'closed', or 'scheduled'
      liftType: string,          // Platform-specific type (e.g., 'GONDOLA', 'CHAIRLIFT')
      openskimap_ids: string[],  // Matched OpenSkiMap lift IDs

      // Static metadata
      capacity: number,          // Persons per hour
      duration: number,          // Ride duration in minutes
      length: number,            // Length in meters
      uphillCapacity: number,    // Uphill capacity
      speed: number,             // Speed in m/s
      arrivalAltitude: number,   // Top altitude in meters
      departureAltitude: number, // Bottom altitude in meters

      // Real-time data
      openingTimesReal: string,  // Actual opening times
      operating: boolean,        // Currently operating
      openingStatus: string,     // Platform-specific status code
      message: string            // Status message (if any)
    }
  ],
  runs: [
    {
      name: string,              // Run name
      status: string,            // 'open', 'closed', or 'scheduled'
      trailType: string,         // Platform-specific type
      level: string,             // Difficulty level (e.g., 'GREEN', 'BLUE', 'RED', 'BLACK')
      openskimap_ids: string[],  // Matched OpenSkiMap run IDs

      // Static metadata
      length: number,            // Length in meters
      surface: string,           // Surface type
      arrivalAltitude: number,   // Bottom altitude in meters
      departureAltitude: number, // Top altitude in meters
      averageSlope: number,      // Average slope in degrees
      exposure: string,          // Sun exposure
      guaranteedSnow: boolean,   // Snow guarantee

      // Real-time data
      openingTimesReal: string,  // Actual opening times
      operating: boolean,        // Currently operating
      openingStatus: string,     // Platform-specific status code
      groomingStatus: string,    // Grooming status
      snowQuality: string,       // Snow quality
      message: string            // Status message (if any)
    }
  ]
}
```

### `getSupportedResorts()`

Get list of all supported resorts.

**Returns:** Array of resort objects:
```javascript
[
  {
    id: string,           // Resort ID
    name: string,         // Resort name
    openskimap_id: string, // OpenSkiMap resort ID
    platform: string      // Data platform (e.g., 'lumiplan')
  }
]
```

### `getResort(resortIdOrOsmId)`

Get configuration for a specific resort.

**Parameters:**
- `resortIdOrOsmId` (string): Resort ID or OpenSkiMap resort ID

**Returns:** Resort configuration object or `null` if not found

## Supported Resorts

Currently supported resorts:

| Resort | Location | OpenSkiMap ID |
|--------|----------|---------------|
| Les Trois Vallées | France | `68b126bc...` |
| Espace Diamant | France | `0345d73f...` |
| Le Grand Domaine | France | `97a14ced...` |
| Les Sybelles | France | `9bba1f0b...` |
| Paradiski | France | `f47f7e05...`, `dec537b6...` |

More resorts are being added regularly. The module is designed to be easily extensible to support additional platforms and resorts.

## OpenSkiMap Integration

All lifts and runs include matched OpenSkiMap IDs for standardized identification:

- **Fuzzy name matching**: Handles name variations using Levenshtein distance
- **Intelligent disambiguation**: Uses lift type and run difficulty to distinguish between duplicates
- **Multiple matches**: Returns arrays of all matching IDs when duplicates exist
- **Type normalization**: Automatically converts platform-specific types to OpenSkiMap standards

## Adding Support for More Resorts

See [CLAUDE.md](./CLAUDE.md) for developer documentation on:
- Adding new resorts to existing platforms
- Implementing new platform fetchers
- Using the XHR Fetcher tool for API discovery
- Architecture and design principles

## Testing

Run the included test script:

```bash
npm test
```

This fetches live data for Les Trois Vallées and displays summary statistics.

## Credits & Data Sources

This project builds on amazing open-source work:

- **[OpenSkiMap](https://openskimap.org/)** - Open-source ski map providing comprehensive resort, lift, and run data. All resort/lift/run IDs and reference data come from OpenSkiMap.

- **[Liftie](https://github.com/pirxpilot/liftie)** ([liftie.info](https://liftie.info/)) - An excellent open-source ski lift status aggregator with 190+ resorts. This project's architecture is inspired by liftie's platform-based approach. If you need a production-ready lift status service with broader coverage, check out liftie!

## License

MIT License - see [LICENSE](./LICENSE) file for details.

## Contributing

Contributions are welcome! To add support for new resorts or platforms:

1. Fork the repository
2. Follow the architecture guidelines in [CLAUDE.md](./CLAUDE.md)
3. Add tests for your changes
4. Submit a pull request

For bug reports or feature requests, please open an issue on GitHub.
