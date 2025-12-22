/**
 * Ski Resort Status Fetcher
 * Main entry point for fetching live ski resort data
 */

const resorts = require('./resorts');
const LumiplanFetcher = require('./fetchers/lumiplan');

// Map of platform names to fetcher classes
const FETCHERS = {
  lumiplan: LumiplanFetcher
};

/**
 * Fetch live status data for a resort
 * @param {string} resortIdOrOsmId - Resort ID or OpenSkiMap ID
 * @returns {Promise<{resort, lifts, runs}>} Live status data
 */
async function fetchResortStatus(resortIdOrOsmId) {
  const config = resorts.findResort(resortIdOrOsmId);

  if (!config) {
    throw new Error(`Resort not found: ${resortIdOrOsmId}`);
  }

  const FetcherClass = FETCHERS[config.platform];

  if (!FetcherClass) {
    throw new Error(`Unsupported platform: ${config.platform}`);
  }

  const fetcher = new FetcherClass(config);
  return await fetcher.fetch();
}

/**
 * Get list of all supported resorts
 * @returns {Array<{id, name, openskimap_id, platform}>}
 */
function getSupportedResorts() {
  return resorts.getAllResorts().map(r => ({
    id: r.id,
    name: r.name,
    openskimap_id: r.openskimap_id,
    platform: r.platform
  }));
}

/**
 * Get resort configuration
 * @param {string} resortIdOrOsmId - Resort ID or OpenSkiMap ID
 * @returns {Object|null} Resort configuration
 */
function getResort(resortIdOrOsmId) {
  return resorts.findResort(resortIdOrOsmId);
}

module.exports = {
  fetchResortStatus,
  getSupportedResorts,
  getResort,
  fetchers: {
    LumiplanFetcher
  }
};
