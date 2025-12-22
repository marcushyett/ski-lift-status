#!/usr/bin/env node

/**
 * CLI tool for fetching Lumiplan ski data
 *
 * Usage:
 *   node src/cli.js <map-id> [options]
 *
 * Examples:
 *   node src/cli.js tignes-valdisere
 *   node src/cli.js paradiski --lifts-only
 *   node src/cli.js les-3-vallees --summary
 */

import { getSkiAreaData, getLiftStatus, getRunStatus, getAvailableMaps, LUMIPLAN_MAPS } from './index.js';

const args = process.argv.slice(2);

// Show help
if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
  console.log(`
Lumiplan Ski Data CLI

Usage:
  node src/cli.js <map-id> [options]

Available Maps:
${Object.entries(LUMIPLAN_MAPS).map(([id, config]) => `  ${id.padEnd(20)} ${config.displayName}`).join('\n')}

Options:
  --summary       Show summary only (lift/run counts)
  --lifts-only    Show only lift data
  --runs-only     Show only run data
  --json          Output as JSON
  --help, -h      Show this help

Examples:
  node src/cli.js tignes-valdisere
  node src/cli.js paradiski --summary
  node src/cli.js les-3-vallees --json
`);
  process.exit(0);
}

const mapId = args[0];
const showSummary = args.includes('--summary');
const liftsOnly = args.includes('--lifts-only');
const runsOnly = args.includes('--runs-only');
const jsonOutput = args.includes('--json');

async function main() {
  try {
    if (!LUMIPLAN_MAPS[mapId]) {
      console.error(`Error: Unknown map ID '${mapId}'`);
      console.error('Available maps:', Object.keys(LUMIPLAN_MAPS).join(', '));
      process.exit(1);
    }

    console.error(`Fetching data for ${LUMIPLAN_MAPS[mapId].displayName}...`);

    if (showSummary) {
      const [liftStatus, runStatus] = await Promise.all([
        getLiftStatus(mapId),
        getRunStatus(mapId)
      ]);

      if (jsonOutput) {
        console.log(JSON.stringify({ lifts: liftStatus, runs: runStatus }, null, 2));
      } else {
        console.log('\n=== Lift Status ===');
        console.log(`Total: ${liftStatus.total}`);
        console.log(`Open: ${liftStatus.open} (${liftStatus.openPercentage}%)`);
        console.log(`Closed: ${liftStatus.closed}`);
        console.log(`Scheduled: ${liftStatus.scheduled}`);

        console.log('\n=== Run Status ===');
        console.log(`Total: ${runStatus.total}`);
        console.log(`Open: ${runStatus.open} (${runStatus.openPercentage}%)`);
        console.log('\nBy Difficulty:');
        for (const [diff, counts] of Object.entries(runStatus.byDifficulty)) {
          const pct = counts.total > 0 ? Math.round((counts.open / counts.total) * 100) : 0;
          console.log(`  ${diff}: ${counts.open}/${counts.total} (${pct}%)`);
        }
      }
    } else {
      const data = await getSkiAreaData(mapId, { matchOsm: true });

      if (jsonOutput) {
        if (liftsOnly) {
          console.log(JSON.stringify(data.lifts, null, 2));
        } else if (runsOnly) {
          console.log(JSON.stringify(data.runs, null, 2));
        } else {
          console.log(JSON.stringify(data, null, 2));
        }
      } else {
        if (!runsOnly) {
          console.log('\n=== Lifts ===');
          console.log(`Total: ${data.lifts.length}`);
          console.log('');
          for (const lift of data.lifts.slice(0, 20)) {
            const osmInfo = lift.osmMatch ? ` [OSM: ${lift.osmMatch.osmId.slice(0, 8)}...]` : '';
            console.log(`  [${(lift.status || 'unknown').padEnd(10)}] ${lift.name}${osmInfo}`);
          }
          if (data.lifts.length > 20) {
            console.log(`  ... and ${data.lifts.length - 20} more`);
          }
        }

        if (!liftsOnly) {
          console.log('\n=== Runs ===');
          console.log(`Total: ${data.runs.length}`);
          console.log('');
          for (const run of data.runs.slice(0, 20)) {
            const osmInfo = run.osmMatch ? ` [OSM: ${run.osmMatch.osmId.slice(0, 8)}...]` : '';
            const diff = run.difficulty ? `(${run.difficulty})` : '';
            console.log(`  [${(run.status || 'unknown').padEnd(10)}] ${run.name} ${diff}${osmInfo}`);
          }
          if (data.runs.length > 20) {
            console.log(`  ... and ${data.runs.length - 20} more`);
          }
        }

        console.log('\n=== Metadata ===');
        console.log(`Fetched at: ${data.metadata.fetchedAt}`);
        console.log(`Language: ${data.metadata.language}`);
      }
    }
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
}

main();
