#!/usr/bin/env node

/**
 * Ski Lift Status CLI
 *
 * Test a ski resort by OpenSkiMap ID and see what data is available.
 *
 * Usage:
 *   npx ski-lift-status <openskimap-id>
 *   npx ski-lift-status --list
 *   npx ski-lift-status --search <name>
 */

const fs = require('fs');
const path = require('path');

// Paths
const rootDir = path.join(__dirname, '..');
const dataDir = path.join(rootDir, 'data');
const configsDir = path.join(rootDir, 'src/ski_lift_status/configs');
const resortsDir = path.join(configsDir, 'resorts');

/**
 * Parse CSV file into array of objects
 */
function parseCSV(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');
  // Handle both Unix and Windows line endings
  const lines = content.trim().replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  const headers = lines[0].split(',');

  return lines.slice(1).map(line => {
    // Handle quoted values with commas
    const values = [];
    let current = '';
    let inQuotes = false;

    for (const char of line) {
      if (char === '"') {
        inQuotes = !inQuotes;
      } else if (char === ',' && !inQuotes) {
        values.push(current);
        current = '';
      } else {
        current += char;
      }
    }
    values.push(current);

    const obj = {};
    headers.forEach((h, i) => {
      obj[h] = values[i] || '';
    });
    return obj;
  });
}

/**
 * Load OpenSkiMap data
 */
function loadOpenSkiMapData() {
  const liftsPath = path.join(dataDir, 'lifts.csv');
  const runsPath = path.join(dataDir, 'runs.csv');

  const lifts = fs.existsSync(liftsPath) ? parseCSV(liftsPath) : [];
  const runs = fs.existsSync(runsPath) ? parseCSV(runsPath) : [];

  return { lifts, runs };
}

/**
 * Load resort configs
 */
function loadResortConfigs() {
  const resorts = [];

  if (!fs.existsSync(resortsDir)) {
    return resorts;
  }

  const files = fs.readdirSync(resortsDir).filter(f => f.endsWith('.json'));

  for (const file of files) {
    try {
      const config = JSON.parse(fs.readFileSync(path.join(resortsDir, file), 'utf8'));
      resorts.push(config);
    } catch (e) {
      // Skip invalid files
    }
  }

  return resorts;
}

/**
 * Find ski area info by OpenSkiMap ID
 */
function findSkiArea(openskimapId, osmData) {
  // Find all lifts belonging to this ski area
  const lifts = osmData.lifts.filter(l => {
    const ids = (l.ski_area_ids || '').split(';');
    return ids.includes(openskimapId);
  });

  // Find all runs belonging to this ski area
  const runs = osmData.runs.filter(r => {
    const ids = (r.ski_area_ids || '').split(';');
    return ids.includes(openskimapId);
  });

  // Get ski area name from first lift or run
  let areaName = null;
  if (lifts.length > 0) {
    const names = (lifts[0].ski_area_names || '').split(',');
    areaName = names[0];
  } else if (runs.length > 0) {
    const names = (runs[0].ski_area_names || '').split(',');
    areaName = names[0];
  }

  return { lifts, runs, areaName };
}

/**
 * Search for ski areas by name
 */
function searchSkiAreas(query, osmData) {
  const queryLower = query.toLowerCase();
  const matches = new Map();

  // Search lifts
  for (const lift of osmData.lifts) {
    const names = (lift.ski_area_names || '').toLowerCase();
    if (names.includes(queryLower)) {
      const ids = (lift.ski_area_ids || '').split(';');
      const areaNames = (lift.ski_area_names || '').split(',');

      for (let i = 0; i < ids.length; i++) {
        if (!matches.has(ids[i])) {
          matches.set(ids[i], {
            id: ids[i],
            name: areaNames[i] || areaNames[0],
            country: lift.countries,
            region: lift.regions
          });
        }
      }
    }
  }

  return Array.from(matches.values());
}

/**
 * Run extraction for a resort config
 */
async function runExtraction(resortId) {
  // Dynamically load the runner
  const runner = require(path.join(configsDir, 'runner.js'));
  return await runner.extractResort(resortId);
}

/**
 * Display results in a nice format
 */
function displayResults(openskimapId, skiArea, resortConfig, extractedData) {
  console.log('\n' + '='.repeat(60));
  console.log('SKI LIFT STATUS - Resort Analysis');
  console.log('='.repeat(60));

  console.log(`\nOpenSkiMap ID: ${openskimapId}`);
  console.log(`Ski Area Name: ${skiArea.areaName || 'Unknown'}`);

  // OpenSkiMap data
  console.log('\n--- OpenSkiMap Reference Data ---');
  console.log(`Lifts in database: ${skiArea.lifts.length}`);
  console.log(`Runs in database: ${skiArea.runs.length}`);

  if (skiArea.lifts.length > 0) {
    console.log('\nSample lifts:');
    skiArea.lifts.slice(0, 10).forEach(l => {
      console.log(`  - ${l.name || '(unnamed)'} (${l.lift_type})`);
    });
    if (skiArea.lifts.length > 10) {
      console.log(`  ... and ${skiArea.lifts.length - 10} more`);
    }
  }

  // Config status
  console.log('\n--- Configuration Status ---');
  if (resortConfig) {
    console.log(`Config exists: Yes`);
    console.log(`Config ID: ${resortConfig.id}`);
    console.log(`Platform: ${resortConfig.platform}`);
    console.log(`URL: ${resortConfig.url || resortConfig.dataUrl || 'N/A'}`);
  } else {
    console.log(`Config exists: No`);
    console.log(`\nTo add this resort, create a JSON file in:`);
    console.log(`  src/ski_lift_status/configs/resorts/<resort-id>.json`);
  }

  // Extracted data
  if (extractedData) {
    console.log('\n--- Live Extraction Results ---');

    if (extractedData.error) {
      console.log(`Error: ${extractedData.error}`);
    } else if (extractedData.note) {
      console.log(`Note: ${extractedData.note}`);
    } else {
      const openLifts = (extractedData.lifts || []).filter(l => l.status === 'open').length;
      const openRuns = (extractedData.runs || []).filter(r => r.status === 'open').length;

      console.log(`Lifts extracted: ${extractedData.lifts?.length || 0} (${openLifts} open)`);
      console.log(`Runs extracted: ${extractedData.runs?.length || 0} (${openRuns} open)`);

      if (extractedData.lifts && extractedData.lifts.length > 0) {
        console.log('\nLift status:');
        extractedData.lifts.slice(0, 15).forEach(l => {
          const icon = l.status === 'open' ? '\u2713' : l.status === 'scheduled' ? '~' : 'x';
          console.log(`  [${icon}] ${l.name} (${l.status})`);
        });
        if (extractedData.lifts.length > 15) {
          console.log(`  ... and ${extractedData.lifts.length - 15} more`);
        }
      }

      if (extractedData.runs && extractedData.runs.length > 0) {
        console.log('\nRun status (first 10):');
        extractedData.runs.slice(0, 10).forEach(r => {
          const icon = r.status === 'open' ? '\u2713' : r.status === 'scheduled' ? '~' : 'x';
          console.log(`  [${icon}] ${r.name} (${r.status})`);
        });
        if (extractedData.runs.length > 10) {
          console.log(`  ... and ${extractedData.runs.length - 10} more`);
        }
      }
    }
  }

  console.log('\n' + '='.repeat(60) + '\n');
}

/**
 * List all configured resorts
 */
function listResorts(resortConfigs) {
  console.log('\nConfigured Resorts:\n');
  console.log('ID'.padEnd(45) + 'Name'.padEnd(35) + 'Platform');
  console.log('-'.repeat(100));

  for (const config of resortConfigs.sort((a, b) => a.id.localeCompare(b.id))) {
    console.log(
      config.id.padEnd(45) +
      (config.name || '').substring(0, 33).padEnd(35) +
      (config.platform || '')
    );
  }

  console.log(`\nTotal: ${resortConfigs.length} resorts\n`);
}

/**
 * Main function
 */
async function main() {
  const args = process.argv.slice(2);

  if (args.length === 0 || args[0] === '--help' || args[0] === '-h') {
    console.log(`
Ski Lift Status CLI

Usage:
  npx ski-lift-status <openskimap-id>    Test a ski resort by OpenSkiMap ID
  npx ski-lift-status <resort-id>        Test a configured resort by ID
  npx ski-lift-status --list             List all configured resorts
  npx ski-lift-status --search <name>    Search for ski areas by name

Examples:
  npx ski-lift-status 37ee9c6ba5b44864ba844f804938a8b815f8b717
  npx ski-lift-status skiwelt
  npx ski-lift-status --search "La Plagne"
`);
    return;
  }

  // Load data
  const osmData = loadOpenSkiMapData();
  const resortConfigs = loadResortConfigs();

  // Handle --list
  if (args[0] === '--list') {
    listResorts(resortConfigs);
    return;
  }

  // Handle --search
  if (args[0] === '--search') {
    const query = args.slice(1).join(' ');
    if (!query) {
      console.error('Error: Please provide a search query');
      process.exit(1);
    }

    const matches = searchSkiAreas(query, osmData);

    if (matches.length === 0) {
      console.log(`\nNo ski areas found matching "${query}"\n`);
    } else {
      console.log(`\nSki areas matching "${query}":\n`);
      for (const match of matches.slice(0, 20)) {
        console.log(`  ${match.id}`);
        console.log(`    Name: ${match.name}`);
        console.log(`    Location: ${match.region}, ${match.country}`);
        console.log('');
      }
      if (matches.length > 20) {
        console.log(`  ... and ${matches.length - 20} more\n`);
      }
    }
    return;
  }

  // Main lookup flow
  const input = args[0];

  // Check if it's a resort ID (existing config)
  let resortConfig = resortConfigs.find(r => r.id === input);
  let openskimapId = resortConfig?.openskimap_id || null;

  // If not found as resort ID, treat as OpenSkiMap ID
  if (!resortConfig) {
    openskimapId = input;
    resortConfig = resortConfigs.find(r => r.openskimap_id === openskimapId);
  }

  // Look up ski area data
  const skiArea = findSkiArea(openskimapId, osmData);

  if (!skiArea.areaName && skiArea.lifts.length === 0 && skiArea.runs.length === 0) {
    // Maybe it's actually a resort ID that isn't in OpenSkiMap
    if (!resortConfig) {
      console.error(`\nNo ski area found with ID: ${input}`);
      console.error('Use --search to find ski areas by name, or --list to see configured resorts.\n');
      process.exit(1);
    }
  }

  // Run extraction if we have a config
  let extractedData = null;
  if (resortConfig) {
    console.log(`\nExtracting data for ${resortConfig.name}...`);
    try {
      extractedData = await runExtraction(resortConfig.id);
    } catch (e) {
      extractedData = { error: e.message };
    }
  }

  // Display results
  displayResults(openskimapId, skiArea, resortConfig, extractedData);
}

main().catch(e => {
  console.error('Error:', e.message);
  process.exit(1);
});
