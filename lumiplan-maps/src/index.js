/**
 * Lumiplan Ski Data
 *
 * A module for fetching real-time ski resort lift and run data from
 * Lumiplan interactive maps, with fuzzy matching to OpenSkiMap IDs.
 *
 * @example
 * import { getSkiAreaData, LUMIPLAN_MAPS } from 'lumiplan-ski-data';
 *
 * // Get data for Tignes - Val d'Isère
 * const data = await getSkiAreaData('tignes-valdisere');
 * console.log(data.lifts); // Array of lifts with status
 * console.log(data.runs);  // Array of runs with status
 */

import { LUMIPLAN_MAPS, LUMIPLAN_API_BASE } from './config.js';
import { fetchAndMergeData, fetchStaticData, fetchDynamicData } from './fetcher.js';
import { matchAllItems, parseOpenSkiMapCSV, normalizeName } from './matcher.js';
import { readFileSync, existsSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

// Re-export configuration
export { LUMIPLAN_MAPS, LUMIPLAN_API_BASE };
export { normalizeName } from './matcher.js';

// Get the directory of this module
const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Load precomputed OpenSkiMap data for a Lumiplan map
 * @param {string} mapId - Lumiplan map ID (e.g., 'tignes-valdisere')
 * @returns {Object} Object with lifts and runs arrays
 */
function loadOsmData(mapId) {
  const dataDir = join(__dirname, '..', 'data');
  const liftsPath = join(dataDir, `${mapId}-lifts.json`);
  const runsPath = join(dataDir, `${mapId}-runs.json`);

  let lifts = [];
  let runs = [];

  if (existsSync(liftsPath)) {
    lifts = JSON.parse(readFileSync(liftsPath, 'utf-8'));
  }

  if (existsSync(runsPath)) {
    runs = JSON.parse(readFileSync(runsPath, 'utf-8'));
  }

  return { lifts, runs };
}

/**
 * Get ski area data with real-time status
 *
 * @param {string} mapId - Lumiplan map ID (e.g., 'tignes-valdisere', 'paradiski')
 * @param {Object} options - Options
 * @param {string} options.lang - Language code (default: 'en')
 * @param {boolean} options.matchOsm - Whether to match with OpenSkiMap data (default: true)
 * @returns {Promise<Object>} Ski area data with lifts, runs, and metadata
 *
 * @example
 * const data = await getSkiAreaData('tignes-valdisere');
 *
 * // Each lift has:
 * // - id, name, type, status, openingStatus, operating
 * // - capacity, duration, length, arrivalAltitude, departureAltitude
 * // - osmMatch (if matchOsm is true): { osmId, osmName, score, confidence }
 *
 * // Each run has:
 * // - id, name, type, difficulty, status, openingStatus
 * // - length, surface, groomingStatus, snowQuality
 * // - osmMatch (if matchOsm is true): { osmId, osmName, score, confidence }
 */
export async function getSkiAreaData(mapId, options = {}) {
  const { lang = 'en', matchOsm = true } = options;

  const mapConfig = LUMIPLAN_MAPS[mapId];
  if (!mapConfig) {
    const availableMaps = Object.keys(LUMIPLAN_MAPS).join(', ');
    throw new Error(`Unknown map ID: ${mapId}. Available maps: ${availableMaps}`);
  }

  // Fetch and merge Lumiplan data
  const data = await fetchAndMergeData(mapConfig.uuid, lang);

  // Match with OpenSkiMap data if requested and available
  if (matchOsm) {
    const osmData = loadOsmData(mapId);

    if (osmData.lifts.length > 0) {
      data.lifts = matchAllItems(data.lifts, osmData.lifts);
    }

    if (osmData.runs.length > 0) {
      data.runs = matchAllItems(data.runs, osmData.runs);
    }
  }

  // Add map configuration to metadata
  data.metadata.mapId = mapId;
  data.metadata.mapName = mapConfig.mapName;
  data.metadata.displayName = mapConfig.displayName;
  data.metadata.uuid = mapConfig.uuid;
  data.metadata.openSkiMapIds = mapConfig.openSkiMapIds;

  return data;
}

/**
 * Get list of available Lumiplan maps
 * @returns {Array<Object>} Array of map info objects
 */
export function getAvailableMaps() {
  return Object.entries(LUMIPLAN_MAPS).map(([id, config]) => ({
    id,
    name: config.mapName,
    displayName: config.displayName,
    openSkiMapIds: config.openSkiMapIds
  }));
}

/**
 * Get lift status summary for a ski area
 * @param {string} mapId - Lumiplan map ID
 * @returns {Promise<Object>} Summary with counts and percentages
 */
export async function getLiftStatus(mapId) {
  const data = await getSkiAreaData(mapId, { matchOsm: false });

  const total = data.lifts.length;
  const open = data.lifts.filter(l => l.status === 'open').length;
  const closed = data.lifts.filter(l => l.status === 'closed').length;
  const scheduled = data.lifts.filter(l => l.status === 'scheduled').length;

  return {
    total,
    open,
    closed,
    scheduled,
    openPercentage: total > 0 ? Math.round((open / total) * 100) : 0,
    lifts: data.lifts.map(l => ({
      name: l.name,
      type: l.type,
      status: l.status
    }))
  };
}

/**
 * Get run status summary for a ski area
 * @param {string} mapId - Lumiplan map ID
 * @returns {Promise<Object>} Summary with counts by difficulty
 */
export async function getRunStatus(mapId) {
  const data = await getSkiAreaData(mapId, { matchOsm: false });

  const byDifficulty = {};
  for (const run of data.runs) {
    const diff = run.difficulty || 'unknown';
    if (!byDifficulty[diff]) {
      byDifficulty[diff] = { total: 0, open: 0 };
    }
    byDifficulty[diff].total++;
    if (run.status === 'open') {
      byDifficulty[diff].open++;
    }
  }

  const total = data.runs.length;
  const open = data.runs.filter(r => r.status === 'open').length;

  return {
    total,
    open,
    openPercentage: total > 0 ? Math.round((open / total) * 100) : 0,
    byDifficulty,
    runs: data.runs.map(r => ({
      name: r.name,
      difficulty: r.difficulty,
      status: r.status,
      groomingStatus: r.groomingStatus
    }))
  };
}

// Export fetcher functions for advanced usage
export { fetchStaticData, fetchDynamicData, fetchAndMergeData } from './fetcher.js';
export { matchAllItems, parseOpenSkiMapCSV, createMatcher } from './matcher.js';
