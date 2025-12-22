/**
 * Lumiplan Fetcher
 * Fetches live ski resort data from Lumiplan interactive maps
 */

const BaseFetcher = require('../base');
const api = require('./api');
const matcher = require('./matcher');

class LumiplanFetcher extends BaseFetcher {
  /**
   * Create a Lumiplan fetcher
   * @param {Object} config - Resort configuration
   * @param {string} config.id - Resort ID
   * @param {string} config.name - Resort name
   * @param {string} config.openskimap_id - OpenSkiMap resort ID
   * @param {string} config.lumiplanMapId - Lumiplan map UUID
   */
  constructor(config) {
    super(config);

    if (!config.lumiplanMapId) {
      throw new Error('lumiplanMapId is required for Lumiplan fetcher');
    }
  }

  /**
   * Fetch live status data from Lumiplan API
   * @returns {Promise<{resort, lifts, runs}>}
   */
  async fetch() {
    const { lumiplanMapId, openskimap_id } = this.config;

    // Fetch data from Lumiplan API
    const { static: staticData, dynamic: dynamicData } = await api.fetchMapData(lumiplanMapId);

    // Build dynamic status map
    const statusMap = {};
    for (const item of dynamicData.items || []) {
      statusMap[item.id] = item;
    }

    // Load OpenSkiMap reference data for matching
    let refLifts = [];
    let refRuns = [];
    if (openskimap_id) {
      const refData = matcher.loadReferenceData(openskimap_id);
      refLifts = refData.lifts;
      refRuns = refData.runs;
    }

    const lifts = [];
    const runs = [];

    // Process static items
    for (const item of staticData.items || []) {
      const data = item.data || {};
      const { name, type, id } = data;

      if (!name || !type) continue;

      const dynamicItem = statusMap[id] || {};
      const status = this._normalizeStatus(dynamicItem.openingStatus);

      if (type === 'LIFT') {
        const normalizedType = matcher.normalizeLiftType(data.liftType);
        const osmIds = matcher.findMatches(name, refLifts, { type: normalizedType });

        lifts.push({
          name,
          status,
          liftType: data.liftType,
          openskimap_ids: osmIds,
          // Static metadata
          capacity: data.capacity,
          duration: data.duration,
          length: data.length,
          uphillCapacity: data.uphillCapacity,
          speed: data.speed,
          arrivalAltitude: data.arrivalAltitude,
          departureAltitude: data.departureAltitude,
          openingTimesTheoretic: data.openingTimesTheoretic,
          // Dynamic real-time data
          openingTimesReal: dynamicItem.openingTimesReal,
          operating: dynamicItem.operating,
          openingStatus: dynamicItem.openingStatus,
          message: dynamicItem.message?.content
        });
      } else if (type === 'TRAIL') {
        const normalizedDifficulty = matcher.normalizeDifficulty(data.trailLevel);
        const osmIds = matcher.findMatches(name, refRuns, { difficulty: normalizedDifficulty });

        runs.push({
          name,
          status,
          trailType: data.trailType,
          level: data.trailLevel,
          openskimap_ids: osmIds,
          // Static metadata
          length: data.length,
          surface: data.surface,
          arrivalAltitude: data.arrivalAltitude,
          departureAltitude: data.departureAltitude,
          averageSlope: data.averageSlope,
          exposure: data.exposure,
          guaranteedSnow: data.guaranteedSnow,
          openingTimesTheoretic: data.openingTimesTheoretic,
          // Dynamic real-time data
          openingTimesReal: dynamicItem.openingTimesReal,
          operating: dynamicItem.operating,
          openingStatus: dynamicItem.openingStatus,
          groomingStatus: dynamicItem.groomingStatus,
          snowQuality: dynamicItem.snowQuality,
          message: dynamicItem.message?.content
        });
      }
    }

    return {
      resort: {
        id: this.config.id,
        name: this.config.name,
        openskimap_id: this.config.openskimap_id
      },
      lifts,
      runs
    };
  }

  /**
   * Normalize Lumiplan opening status to standard format
   * @private
   */
  _normalizeStatus(apiStatus) {
    switch (apiStatus) {
      case 'OPEN': return 'open';
      case 'FORECAST': return 'scheduled';
      case 'DELAYED': return 'scheduled';
      default: return 'closed';
    }
  }

  /**
   * Get fetcher metadata
   */
  static getMetadata() {
    return {
      platform: 'lumiplan',
      version: '2.0.0',
      description: 'Lumiplan interactive maps fetcher'
    };
  }
}

module.exports = LumiplanFetcher;
