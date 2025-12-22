#!/usr/bin/env node

/**
 * Generate precomputed OpenSkiMap data files for each Lumiplan map
 *
 * This script reads the main ski-lift-status CSV files and extracts
 * the relevant lifts and runs for each configured Lumiplan map.
 *
 * Run this once to generate the data files, then they can be used
 * for offline matching.
 */

import { readFileSync, writeFileSync, existsSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { LUMIPLAN_MAPS } from './config.js';
import { parseOpenSkiMapCSV } from './matcher.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(__dirname, '..');
const skiLiftStatusRoot = join(projectRoot, '..');

const LIFTS_CSV = join(skiLiftStatusRoot, 'data', 'lifts.csv');
const RUNS_CSV = join(skiLiftStatusRoot, 'data', 'runs.csv');
const DATA_DIR = join(projectRoot, 'data');

function loadCSV(path) {
  if (!existsSync(path)) {
    console.warn(`Warning: ${path} not found`);
    return '';
  }
  return readFileSync(path, 'utf-8');
}

function generateOsmData() {
  console.log('Generating OpenSkiMap data files...\n');

  // Load CSV data
  console.log('Loading CSV files...');
  const liftsCSV = loadCSV(LIFTS_CSV);
  const runsCSV = loadCSV(RUNS_CSV);

  if (!liftsCSV && !runsCSV) {
    console.error('No CSV data found. Make sure the ski-lift-status data files exist.');
    process.exit(1);
  }

  // Process each map
  for (const [mapId, config] of Object.entries(LUMIPLAN_MAPS)) {
    console.log(`\nProcessing ${mapId}...`);
    console.log(`  OpenSkiMap IDs: ${config.openSkiMapIds.join(', ')}`);

    // Extract lifts
    const lifts = parseOpenSkiMapCSV(liftsCSV, config.openSkiMapIds);
    console.log(`  Found ${lifts.length} lifts`);

    // Extract runs
    const runs = parseOpenSkiMapCSV(runsCSV, config.openSkiMapIds);
    console.log(`  Found ${runs.length} runs`);

    // Write data files
    const liftsPath = join(DATA_DIR, `${mapId}-lifts.json`);
    const runsPath = join(DATA_DIR, `${mapId}-runs.json`);

    writeFileSync(liftsPath, JSON.stringify(lifts, null, 2));
    writeFileSync(runsPath, JSON.stringify(runs, null, 2));

    console.log(`  Wrote ${liftsPath}`);
    console.log(`  Wrote ${runsPath}`);
  }

  console.log('\nDone!');
}

generateOsmData();
