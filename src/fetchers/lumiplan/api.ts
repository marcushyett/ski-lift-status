/**
 * Lumiplan API Client
 * Fetches data from Lumiplan interactive map endpoints
 */

import * as https from 'https';
import * as http from 'http';

const BASE_URL = 'https://lumiplay.link/interactive-map-services/public/map';
const REQUEST_TIMEOUT = 15000;

/**
 * Lumiplan POI item data structure
 */
export interface LumiplanItemData {
  id?: string;
  name?: string;
  type?: 'LIFT' | 'TRAIL' | string;
  liftType?: string;
  trailType?: string;
  trailLevel?: string;
  capacity?: number;
  duration?: number;
  length?: number;
  uphillCapacity?: number;
  speed?: number;
  arrivalAltitude?: number;
  departureAltitude?: number;
  openingTimesTheoretic?: string;
  surface?: string;
  averageSlope?: number;
  exposure?: string;
  guaranteedSnow?: boolean;
}

/**
 * Lumiplan POI item
 */
export interface LumiplanItem {
  data?: LumiplanItemData;
}

/**
 * Lumiplan static data response
 */
export interface LumiplanStaticData {
  items?: LumiplanItem[];
}

/**
 * Lumiplan dynamic status item
 */
export interface LumiplanDynamicItem {
  id: string;
  openingStatus?: string;
  openingTimesReal?: string;
  operating?: boolean;
  groomingStatus?: string;
  snowQuality?: string;
  message?: {
    content?: string;
  };
}

/**
 * Lumiplan dynamic data response
 */
export interface LumiplanDynamicData {
  items?: LumiplanDynamicItem[];
}

/**
 * Fetch URL content with timeout
 */
async function fetchUrl(url: string, timeoutMs: number = REQUEST_TIMEOUT): Promise<string> {
  return new Promise((resolve, reject) => {
    const protocol = url.startsWith('https') ? https : http;

    const options: http.RequestOptions = {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; SkiLiftStatus/2.0)',
        Accept: 'application/json',
      },
      timeout: timeoutMs,
    };

    const req = protocol.get(url, options, (res) => {
      // Handle redirects
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        fetchUrl(res.headers.location, timeoutMs).then(resolve).catch(reject);
        return;
      }

      let data = '';
      res.on('data', (chunk) => (data += chunk));
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
 */
export async function fetchStaticData(mapId: string, lang: string = 'en'): Promise<LumiplanStaticData> {
  const url = `${BASE_URL}/${mapId}/staticPoiData?lang=${lang}`;
  const json = await fetchUrl(url);
  return JSON.parse(json);
}

/**
 * Fetch dynamic POI data for a Lumiplan map
 */
export async function fetchDynamicData(mapId: string, lang: string = 'en'): Promise<LumiplanDynamicData> {
  const url = `${BASE_URL}/${mapId}/dynamicPoiData?lang=${lang}`;
  const json = await fetchUrl(url);
  return JSON.parse(json);
}

/**
 * Fetch both static and dynamic data in parallel
 */
export async function fetchMapData(
  mapId: string,
  lang: string = 'en'
): Promise<{ static: LumiplanStaticData; dynamic: LumiplanDynamicData }> {
  const [staticData, dynamicData] = await Promise.all([
    fetchStaticData(mapId, lang),
    fetchDynamicData(mapId, lang),
  ]);

  return { static: staticData, dynamic: dynamicData };
}
