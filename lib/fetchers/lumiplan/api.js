/**
 * Lumiplan API Client
 * Fetches data from Lumiplan interactive map endpoints
 */

const https = require('https');
const http = require('http');

const BASE_URL = 'https://lumiplay.link/interactive-map-services/public/map';
const REQUEST_TIMEOUT = 15000;

/**
 * Fetch URL content with timeout
 */
async function fetch(url, timeoutMs = REQUEST_TIMEOUT) {
  return new Promise((resolve, reject) => {
    const protocol = url.startsWith('https') ? https : http;

    const options = {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; SkiLiftStatus/2.0)',
        'Accept': 'application/json'
      },
      timeout: timeoutMs
    };

    const req = protocol.get(url, options, (res) => {
      // Handle redirects
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return fetch(res.headers.location, timeoutMs).then(resolve).catch(reject);
      }

      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data));
    });

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error(`Request timed out after ${timeoutMs}ms`));
    });
  });
}

/**
 * Fetch static POI data for a Lumiplan map
 * @param {string} mapId - Lumiplan map UUID
 * @param {string} lang - Language code (default: 'en')
 * @returns {Promise<Object>} Static POI data with lift/run metadata
 */
async function fetchStaticData(mapId, lang = 'en') {
  const url = `${BASE_URL}/${mapId}/staticPoiData?lang=${lang}`;
  const json = await fetch(url);
  return JSON.parse(json);
}

/**
 * Fetch dynamic POI data for a Lumiplan map
 * @param {string} mapId - Lumiplan map UUID
 * @param {string} lang - Language code (default: 'en')
 * @returns {Promise<Object>} Dynamic POI data with real-time status
 */
async function fetchDynamicData(mapId, lang = 'en') {
  const url = `${BASE_URL}/${mapId}/dynamicPoiData?lang=${lang}`;
  const json = await fetch(url);
  return JSON.parse(json);
}

/**
 * Fetch both static and dynamic data in parallel
 * @param {string} mapId - Lumiplan map UUID
 * @param {string} lang - Language code (default: 'en')
 * @returns {Promise<{static: Object, dynamic: Object}>}
 */
async function fetchMapData(mapId, lang = 'en') {
  const [staticData, dynamicData] = await Promise.all([
    fetchStaticData(mapId, lang),
    fetchDynamicData(mapId, lang)
  ]);

  return { static: staticData, dynamic: dynamicData };
}

module.exports = {
  fetchStaticData,
  fetchDynamicData,
  fetchMapData
};
