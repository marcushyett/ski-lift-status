/**
 * Lumiplan Data Fetcher
 * Fetches and merges static and dynamic POI data from Lumiplan API
 */

import { LUMIPLAN_API_BASE, LIFT_TYPE_MAP, TRAIL_DIFFICULTY_MAP, OPENING_STATUS_MAP } from './config.js';

/**
 * Fetch static POI data for a map
 * @param {string} uuid - Lumiplan map UUID
 * @param {string} lang - Language code (default: 'en')
 * @returns {Promise<Object>} Static POI data
 */
export async function fetchStaticData(uuid, lang = 'en') {
  const url = `${LUMIPLAN_API_BASE}/${uuid}/staticPoiData?lang=${lang}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Failed to fetch static data: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch dynamic POI data for a map
 * @param {string} uuid - Lumiplan map UUID
 * @param {string} lang - Language code (default: 'en')
 * @returns {Promise<Object>} Dynamic POI data
 */
export async function fetchDynamicData(uuid, lang = 'en') {
  const url = `${LUMIPLAN_API_BASE}/${uuid}/dynamicPoiData?lang=${lang}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Failed to fetch dynamic data: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch map metadata
 * @param {string} mapName - Lumiplan map name
 * @returns {Promise<Object>} Map metadata
 */
export async function fetchMapMetadata(mapName) {
  const url = `${LUMIPLAN_API_BASE}/name/${mapName}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Failed to fetch map metadata: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

/**
 * Extract lifts from static data
 * @param {Object} staticData - Raw static POI data
 * @returns {Map<number, Object>} Map of lift ID to lift data
 */
export function extractLifts(staticData) {
  const lifts = new Map();

  for (const item of staticData.items || []) {
    if (item.data?.type === 'LIFT') {
      const lift = {
        id: item.data.id,
        name: item.data.name,
        type: LIFT_TYPE_MAP[item.data.liftType] || item.data.liftType?.toLowerCase(),
        liftType: item.data.liftType,
        capacity: item.data.capacity,
        duration: item.data.duration,
        length: item.data.length,
        uphillCapacity: item.data.uphillCapacity,
        arrivalAltitude: item.data.arrivalAltitude,
        departureAltitude: item.data.departureAltitude,
        openingTimes: item.data.openingTimesTheoretic,
        coordinates: { x: item.x, y: item.y }
      };
      lifts.set(item.data.id, lift);
    }
  }

  return lifts;
}

/**
 * Extract runs/trails from static data
 * @param {Object} staticData - Raw static POI data
 * @returns {Map<number, Object>} Map of trail ID to trail data
 */
export function extractRuns(staticData) {
  const runs = new Map();

  for (const item of staticData.items || []) {
    if (item.data?.type === 'TRAIL') {
      const run = {
        id: item.data.id,
        name: item.data.name,
        type: item.data.trailType?.toLowerCase(),
        difficulty: TRAIL_DIFFICULTY_MAP[item.data.trailLevel] || item.data.trailLevel?.toLowerCase(),
        trailLevel: item.data.trailLevel,
        length: item.data.length,
        surface: item.data.surface,
        arrivalAltitude: item.data.arrivalAltitude,
        departureAltitude: item.data.departureAltitude,
        guaranteedSnow: item.data.guaranteedSnow,
        openingTimes: item.data.openingTimesTheoretic,
        coordinates: { x: item.x, y: item.y }
      };
      runs.set(item.data.id, run);
    }
  }

  return runs;
}

/**
 * Merge dynamic status data into items
 * @param {Map<number, Object>} items - Static items (lifts or runs)
 * @param {Array<Object>} dynamicItems - Dynamic status items
 * @returns {Map<number, Object>} Items with status merged
 */
export function mergeDynamicData(items, dynamicItems) {
  const statusMap = new Map();

  for (const dynItem of dynamicItems) {
    statusMap.set(dynItem.id, dynItem);
  }

  for (const [id, item] of items) {
    const status = statusMap.get(id);
    if (status) {
      item.status = OPENING_STATUS_MAP[status.openingStatus] || status.openingStatus?.toLowerCase();
      item.openingStatus = status.openingStatus;
      item.operating = status.operating;
      item.message = status.message?.content;

      // Run-specific status fields
      if (status.groomingStatus) {
        item.groomingStatus = status.groomingStatus;
      }
      if (status.snowQuality) {
        item.snowQuality = status.snowQuality;
      }
    }
  }

  return items;
}

/**
 * Fetch and merge all data for a Lumiplan map
 * @param {string} uuid - Lumiplan map UUID
 * @param {string} lang - Language code
 * @returns {Promise<Object>} Complete ski area data with lifts and runs
 */
export async function fetchAndMergeData(uuid, lang = 'en') {
  // Fetch both datasets in parallel
  const [staticData, dynamicData] = await Promise.all([
    fetchStaticData(uuid, lang),
    fetchDynamicData(uuid, lang)
  ]);

  // Extract items
  const lifts = extractLifts(staticData);
  const runs = extractRuns(staticData);

  // Merge dynamic status
  const dynamicItems = dynamicData.items || [];
  mergeDynamicData(lifts, dynamicItems);
  mergeDynamicData(runs, dynamicItems);

  // Get totals from dynamic data
  const totals = dynamicData.totals || [];

  // Get resort info
  const resorts = staticData.resorts || [];

  return {
    lifts: Array.from(lifts.values()),
    runs: Array.from(runs.values()),
    resorts,
    totals,
    metadata: {
      fetchedAt: new Date().toISOString(),
      language: lang
    }
  };
}
