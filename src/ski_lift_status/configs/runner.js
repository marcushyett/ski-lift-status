/**
 * Config Runner
 * Executes resort configs and extracts lift/run status
 *
 * This is a standalone Node.js module that can be run independently
 * to test configs without the full Python pipeline.
 */

const https = require('https');
const http = require('http');
const { JSDOM } = require('jsdom');
const vm = require('vm');
const { URL } = require('url');

// Try to load proxy agent if available
let HttpsProxyAgent;
try {
  HttpsProxyAgent = require('https-proxy-agent').HttpsProxyAgent;
} catch (e) {
  // Proxy agent not available
}

// Load configs from individual files
const resortsConfig = require('./resorts/index.js');
const resorts = resortsConfig.resorts;

// Status normalization helpers
const STATUS_OPEN = ['open', 'ouvert', 'aperto', 'offen', 'abierto', 'O', 'A', '1'];
const STATUS_SCHEDULED = ['scheduled', 'prevision', 'programmato', 'geplant', 'P'];

function normalizeStatus(raw) {
  if (!raw) return 'closed';
  const s = String(raw).toLowerCase().trim();
  if (STATUS_OPEN.some(x => s.includes(x.toLowerCase()))) return 'open';
  if (STATUS_SCHEDULED.some(x => s.includes(x.toLowerCase()))) return 'scheduled';
  return 'closed';
}

/**
 * Get proxy agent if environment proxy is configured
 */
function getProxyAgent(targetUrl) {
  const proxyUrl = process.env.https_proxy || process.env.HTTPS_PROXY ||
                   process.env.http_proxy || process.env.HTTP_PROXY;

  if (!proxyUrl || !HttpsProxyAgent) return null;

  // Check no_proxy
  const noProxy = process.env.no_proxy || process.env.NO_PROXY || '';
  const targetHost = new URL(targetUrl).hostname;
  const noProxyList = noProxy.split(',').map(s => s.trim());

  for (const pattern of noProxyList) {
    if (!pattern) continue;
    if (pattern === targetHost) return null;
    if (pattern.startsWith('*') && targetHost.endsWith(pattern.slice(1))) return null;
  }

  return new HttpsProxyAgent(proxyUrl);
}

// Concurrency settings for parallel execution
const CONCURRENCY_LIMIT = 20;  // Number of parallel requests
const REQUEST_TIMEOUT_MS = 15000;  // 15 second timeout per request

/**
 * Fetch URL content with timeout
 */
async function fetch(url, timeoutMs = REQUEST_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const protocol = url.startsWith('https') ? https : http;
    const agent = getProxyAgent(url);

    const options = {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; SkiLiftStatus/1.0)',
        'Accept': 'text/html,application/json'
      },
      timeout: timeoutMs
    };

    if (agent) {
      options.agent = agent;
    }

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
 * Fetch URL with POST method
 */
async function fetchPost(url, body, timeoutMs = REQUEST_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const parsedUrl = new URL(url);
    const protocol = url.startsWith('https') ? https : http;
    const agent = getProxyAgent(url);
    const postData = typeof body === 'string' ? body : JSON.stringify(body);

    const options = {
      hostname: parsedUrl.hostname,
      port: parsedUrl.port || (url.startsWith('https') ? 443 : 80),
      path: parsedUrl.pathname + parsedUrl.search,
      method: 'POST',
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; SkiLiftStatus/1.0)',
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData),
        'Accept': 'application/json'
      },
      timeout: timeoutMs
    };

    if (agent) {
      options.agent = agent;
    }

    const req = protocol.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data));
    });

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error(`Request timed out after ${timeoutMs}ms`));
    });

    req.write(postData);
    req.end();
  });
}

/**
 * Extract __NUXT__ data from HTML
 *
 * Handles multiple Nuxt.js data formats:
 * 1. Simple object: window.__NUXT__ = {...}
 * 2. IIFE format: window.__NUXT__ = (function(a,b,...){return {...}})(val1,val2,...)
 */
function extractNuxtData(html) {
  // Try multiple patterns for different Nuxt versions

  // Pattern 1: IIFE format (e.g., Cervinia)
  // Match from window.__NUXT__ to the closing );
  const iifeMatch = html.match(/window\.__NUXT__\s*=\s*(\(function\([^)]*\)\{[\s\S]*?\}\)\([^;]*\));/);
  if (iifeMatch) {
    try {
      const context = { window: {} };
      vm.runInNewContext(`window.__NUXT__ = ${iifeMatch[1]}`, context);
      return context.window.__NUXT__;
    } catch (e) {
      console.error('Failed to parse IIFE __NUXT__:', e.message);
    }
  }

  // Pattern 2: Try extracting just the script containing __NUXT__
  const scriptMatch = html.match(/<script[^>]*>([^<]*window\.__NUXT__[^<]*)<\/script>/);
  if (scriptMatch) {
    try {
      const context = { window: {} };
      vm.runInNewContext(scriptMatch[1], context);
      return context.window.__NUXT__;
    } catch (e) {
      console.error('Failed to parse script __NUXT__:', e.message);
    }
  }

  // Pattern 3: Simple object format
  const simpleMatch = html.match(/window\.__NUXT__\s*=\s*(\{[\s\S]*?\});/);
  if (simpleMatch) {
    try {
      const context = { window: {} };
      vm.runInNewContext(`window.__NUXT__ = ${simpleMatch[1]}`, context);
      return context.window.__NUXT__;
    } catch (e) {
      console.error('Failed to parse simple __NUXT__:', e.message);
    }
  }

  return null;
}

/**
 * Extract data using JSONPath-like selector
 */
function extractByPath(data, path) {
  const parts = path.replace(/^\$\./, '').split(/[\.\[\]]+/).filter(Boolean);
  let current = data;

  for (const part of parts) {
    if (part === '*') {
      // Wildcard - collect all items
      if (Array.isArray(current)) {
        return current.flatMap(item => extractByPath(item, parts.slice(parts.indexOf('*') + 1).join('.')));
      }
      return [];
    }
    if (current === null || current === undefined) return [];
    current = current[part];
  }

  return Array.isArray(current) ? current : [current];
}

/**
 * Extract nested path from object (e.g., "@attributes.nom")
 */
function getNestedValue(obj, path) {
  const parts = path.split('.');
  let current = obj;
  for (const part of parts) {
    if (current === null || current === undefined) return null;
    current = current[part];
  }
  return current;
}

/**
 * Extract using Lumiplan JSON API (preferred) or HTML bulletin (fallback)
 * JSON API provides both lifts AND runs with accurate status
 * HTML bulletin may only have lifts for older format pages
 */
async function extractLumiplan(config) {
  // If we have a lumiplanMapId, use the JSON API (preferred)
  if (config.lumiplanMapId) {
    return await extractLumiplanJson(config);
  }

  // Otherwise fall back to HTML parsing
  return await extractLumiplanHtml(config);
}

/**
 * Extract using Lumiplan JSON API
 * Endpoints: /staticPoiData (names, types) and /dynamicPoiData (status)
 */
async function extractLumiplanJson(config) {
  const baseUrl = 'https://lumiplay.link/interactive-map-services/public/map';
  const mapId = config.lumiplanMapId;

  // Fetch static and dynamic data in parallel
  const [staticJson, dynamicJson] = await Promise.all([
    fetch(`${baseUrl}/${mapId}/staticPoiData?lang=en`),
    fetch(`${baseUrl}/${mapId}/dynamicPoiData?lang=en`)
  ]);

  let staticData, dynamicData;
  try {
    staticData = JSON.parse(staticJson);
    dynamicData = JSON.parse(dynamicJson);
  } catch (e) {
    return { error: 'Failed to parse Lumiplan JSON API response' };
  }

  // Build status map from dynamic data (id -> openingStatus)
  const statusMap = {};
  for (const item of dynamicData.items || []) {
    statusMap[item.id] = item.openingStatus;
  }

  // Normalize Lumiplan status to our format
  function normalizeApiStatus(apiStatus) {
    switch (apiStatus) {
      case 'OPEN': return 'open';
      case 'FORECAST': return 'scheduled';
      case 'DELAYED': return 'scheduled';
      default: return 'closed'; // CLOSED, OUT_OF_PERIOD, etc.
    }
  }

  const lifts = [];
  const runs = [];

  // Process static items
  for (const item of staticData.items || []) {
    const data = item.data || {};
    const name = data.name;
    const type = data.type;
    const id = data.id;

    if (!name || !type) continue;

    const apiStatus = statusMap[id] || 'UNKNOWN';
    const status = normalizeApiStatus(apiStatus);

    if (type === 'LIFT') {
      lifts.push({ name, status, liftType: data.liftType });
    } else if (type === 'TRAIL') {
      runs.push({ name, status, trailType: data.trailType, level: data.trailLevel });
    }
  }

  return { lifts, runs };
}

/**
 * Extract using Lumiplan HTML bulletin (fallback for resorts without JSON API)
 * Supports both old format (prl_group) and new format (POI_info)
 */
async function extractLumiplanHtml(config) {
  const dataUrl = config.dataUrl;
  if (!dataUrl) return { error: 'No dataUrl specified' };

  const html = await fetch(dataUrl);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];
  const runs = [];

  // Lift type patterns (for classification)
  const liftTypes = [
    'CHAIRLIFT', 'DETACHABLE_CHAIRLIFT', 'GONDOLA', 'FUNITEL', 'TRAM',
    'SURFACE_LIFT', 'MAGIC_CARPET', 'ROPE_TOW', 'CABLE_CAR',
    // Old format codes
    'TC', 'TB', 'TSD', 'TSDB', 'TS', 'TK', 'TR', 'FUN', 'TPH', 'DMC', 'TM'
  ];

  // Run/trail type patterns
  const runTypes = [
    'DOWNHILL_SKIING', 'CROSS_COUNTRY', 'SLEDDING', 'SNOWSHOE',
    'SKI_TOURING', 'BOARDERCROSS', 'SNOWPARK', 'FUN_ZONE',
    // Old format codes: DH=Downhill, XC=Cross-country, VE=Enduro, A=Alpine, F=Nordic
    // Suffixes: V=Green, B=Blue, R=Red, N=Black, J=Yellow
    'DH-V', 'DH-B', 'DH-R', 'DH-N', 'DH-J',
    'XC-V', 'XC-B', 'XC-R', 'XC-N',
    'VE-V', 'VE-B', 'VE-R', 'VE-N',
    'A-V', 'A-B', 'A-R', 'A-N',
    'F-V', 'F-B', 'F-R', 'F-N',
    '/DH', '/XC', '/VE', '/A-', '/F-'  // Partial matches for type images
  ];

  // Parse status from image src
  function parseStatus(src) {
    if (!src) return 'closed';
    // New format: lp_runway_trail_opened.svg, lp_runway_trail_scheduled.svg, lp_runway_trail_closed.svg
    if (src.includes('_opened') || src.includes('_open')) return 'open';
    if (src.includes('_scheduled')) return 'scheduled';
    if (src.includes('_closed')) return 'closed';
    // Old format: etats/O.svg, etats/F.svg, etats/H.svg, etats/P.svg
    const match = src.match(/etats\/([A-Z])\.svg$/i);
    if (match) {
      const code = match[1].toUpperCase();
      if (code === 'O' || code === 'A') return 'open';
      if (code === 'P') return 'scheduled';
    }
    return 'closed';
  }

  // Classify item as lift or run based on type image
  function isLiftType(typeSrc) {
    if (!typeSrc) return true; // Default to lift if unknown
    return liftTypes.some(t => typeSrc.toUpperCase().includes(t));
  }

  function isRunType(typeSrc) {
    if (!typeSrc) return false;
    const upper = typeSrc.toUpperCase();
    // Check for explicit run patterns
    if (runTypes.some(t => upper.includes(t.toUpperCase()))) return true;
    // Also check for skiing/trail indicators
    if (upper.includes('PISTE') || upper.includes('TRAIL') || upper.includes('SKIING') ||
        upper.includes('RUNWAY') || upper.includes('SLOPE')) return true;
    return false;
  }

  // Try NEW format first: POI_info (La Plagne, etc.)
  const poiItems = doc.querySelectorAll('.POI_info');
  if (poiItems.length > 0) {
    poiItems.forEach(item => {
      const nameEl = item.querySelector('.nom, span.nom');
      const typeImg = item.querySelector('img.img_type');
      // Get the last img_status (the opening status, not damage status)
      const statusImgs = item.querySelectorAll('img.img_status');
      const statusImg = statusImgs[statusImgs.length - 1];

      const name = nameEl?.textContent?.trim().replace(/\.$/, '');
      if (!name) return;

      const typeSrc = typeImg?.getAttribute('src') || '';
      const statusSrc = statusImg?.getAttribute('src') || '';
      const status = parseStatus(statusSrc);

      // Skip non-ski items (restaurants, pedestrian paths, etc.)
      if (typeSrc.includes('RESTAURANT') || typeSrc.includes('PEDESTRIAN') ||
          typeSrc.includes('AEROLIVE') || typeSrc.includes('UNDEF')) {
        return;
      }

      if (isRunType(typeSrc)) {
        runs.push({ name, status });
      } else if (isLiftType(typeSrc)) {
        lifts.push({ name, status });
      }
    });
  }

  // Try OLD format: prl_group (Trois Vallées bulletin - lifts only)
  if (lifts.length === 0 && runs.length === 0) {
    const groups = doc.querySelectorAll('.prl_group[title]');
    groups.forEach(group => {
      const name = group.getAttribute('title')?.trim().replace(/\.$/, '');
      const typeImg = group.querySelector('img.img_type');
      const statusImg = group.querySelector('img.image_status') ||
                        group.parentElement?.querySelector('img.image_status');

      if (!name) return;

      const typeSrc = typeImg?.getAttribute('src') || '';
      const statusSrc = statusImg?.getAttribute('src') || '';
      const status = parseStatus(statusSrc);

      // Old format mostly has lifts, but check for run types
      if (isRunType(typeSrc)) {
        runs.push({ name, status });
      } else {
        lifts.push({ name, status });
      }
    });
  }

  return { lifts, runs };
}

/**
 * Extract using SKIPLAN XML API
 * Used by some French resorts (Avoriaz, etc.) that expose SKIPLAN data
 */
async function extractSkiplanXml(config) {
  const dataUrl = config.dataUrl;
  if (!dataUrl) return { error: 'No dataUrl specified for SKIPLAN XML' };

  const xml = await fetch(dataUrl);

  // Parse the XML response
  const lifts = [];
  const runs = [];

  // Extract REMONTEE (lifts) - attributes may be escaped with \
  const liftMatches = xml.matchAll(/<REMONTEE\s+nom=\\?"([^"\\]+)\\?"\s+etat=\\?"([^"\\]+)\\?"/g);
  for (const match of liftMatches) {
    const name = match[1].replace(/&apos;/g, "'").replace(/&amp;/g, '&');
    const status = match[2] === 'O' ? 'open' : match[2] === 'P' ? 'scheduled' : 'closed';
    lifts.push({ name, status });
  }

  // Extract PISTE (runs) - attributes may be escaped with \
  const runMatches = xml.matchAll(/<PISTE\s+nom=\\?"([^"\\]+)\\?"\s+etat=\\?"([^"\\]+)\\?"/g);
  for (const match of runMatches) {
    const name = match[1].replace(/&apos;/g, "'").replace(/&amp;/g, '&');
    const status = match[2] === 'O' ? 'open' : match[2] === 'P' ? 'scheduled' : 'closed';
    runs.push({ name, status });
  }

  return { lifts, runs };
}

/**
 * Extract using Nuxt.js embedded data
 */
async function extractNuxt(config) {
  const html = await fetch(config.url);
  const nuxtData = extractNuxtData(html);

  if (!nuxtData) {
    return { error: 'Failed to extract __NUXT__ data' };
  }

  const cfg = config.config || {};
  const liftsPath = cfg.lifts || '$.state.impianti.SECTEUR[*].REMONTEE[*]';
  const runsPath = cfg.runs || '$.state.impianti.SECTEUR[*].PISTE[*]';
  const namePath = cfg.name || '@attributes.nom';
  const statusPath = cfg.status || '@attributes.etat';
  const statusMap = cfg.statusMap || { O: 'open', A: 'open', F: 'closed', P: 'scheduled' };

  const extractItems = (path) => {
    const items = [];
    const rawItems = extractByPath(nuxtData, path);

    rawItems.forEach(item => {
      if (!item) return;
      const name = getNestedValue(item, namePath);
      const rawStatus = getNestedValue(item, statusPath);
      const status = statusMap[rawStatus] || 'closed';

      if (name) {
        items.push({ name, status, raw: item });
      }
    });

    return items;
  };

  return {
    lifts: extractItems(liftsPath),
    runs: extractItems(runsPath)
  };
}

/**
 * Extract using Dolomiti Superski
 */
async function extractDolomiti(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];
  const rows = doc.querySelectorAll('.table tbody tr');

  rows.forEach(row => {
    const cells = row.querySelectorAll('td');
    if (cells.length >= 4) {
      const name = cells[1]?.textContent?.trim();
      const statusClass = cells[3]?.className || '';
      const status = statusClass.includes('green') ? 'open' : 'closed';

      if (name) {
        lifts.push({ name, status });
      }
    }
  });

  return { lifts, runs: [] };
}

/**
 * Extract using Skiplan JSON API
 * Used by Paradiski resorts (La Plagne, Les Arcs)
 */
async function extractSkiplan(config) {
  if (!config.dataUrl) {
    return { error: 'No dataUrl specified for Skiplan' };
  }

  const json = await fetch(config.dataUrl);
  let data;
  try {
    data = JSON.parse(json);
  } catch (e) {
    return { error: 'Failed to parse Skiplan JSON' };
  }

  const lifts = [];
  const runs = [];

  // Skiplan API typically returns arrays of lifts and pistes
  if (data.remontees || data.lifts) {
    const liftData = data.remontees || data.lifts || [];
    liftData.forEach(item => {
      const name = item.nom || item.name || item.libelle;
      const status = normalizeStatus(item.etat || item.status || item.ouverture);
      if (name) lifts.push({ name, status });
    });
  }

  if (data.pistes || data.runs) {
    const runData = data.pistes || data.runs || [];
    runData.forEach(item => {
      const name = item.nom || item.name || item.libelle;
      const status = normalizeStatus(item.etat || item.status || item.ouverture);
      if (name) runs.push({ name, status });
    });
  }

  return { lifts, runs };
}

/**
 * Extract using Vail Resorts TerrainStatusFeed
 * Inspired by liftie vail.js
 */
async function extractVail(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const statuses = ['closed', 'open', 'hold', 'scheduled'];
  const lifts = [];
  const runs = [];

  // Find script containing TerrainStatusFeed
  const scripts = doc.querySelectorAll('script');

  scripts.forEach(script => {
    const text = script.textContent || '';
    if (text.includes('TerrainStatusFeed')) {
      try {
        const context = { FR: {} };
        vm.runInNewContext(text, context);
        const feed = context.FR?.TerrainStatusFeed;

        if (feed) {
          // Handle GroomingAreas structure (newer format)
          if (feed.GroomingAreas && Array.isArray(feed.GroomingAreas)) {
            feed.GroomingAreas.forEach(area => {
              // Extract lifts
              if (area.Lifts && Array.isArray(area.Lifts)) {
                area.Lifts.forEach(lift => {
                  const liftData = {
                    name: lift.Name?.trim(),
                    status: statuses[lift.Status] || 'closed'
                  };

                  // Add optional fields if available
                  if (lift.WaitTimeInMinutes != null) liftData.waitTime = lift.WaitTimeInMinutes;
                  if (lift.Capacity) liftData.capacity = lift.Capacity;
                  if (lift.OpenTime) liftData.openTime = lift.OpenTime;
                  if (lift.CloseTime) liftData.closeTime = lift.CloseTime;

                  lifts.push(liftData);
                });
              }
              // Extract trails/runs
              if (area.Trails && Array.isArray(area.Trails)) {
                area.Trails.forEach(trail => {
                  const runData = {
                    name: trail.Name?.trim(),
                    status: trail.IsOpen ? 'open' : 'closed'
                  };

                  // Add grooming status if available
                  if (trail.IsGroomed != null) runData.groomed = trail.IsGroomed;

                  runs.push(runData);
                });
              }
            });
          }
          // Handle flat Lifts array (older format)
          else if (feed.Lifts && Array.isArray(feed.Lifts)) {
            feed.Lifts.forEach(({ Name, Status }) => {
              lifts.push({
                name: Name?.trim(),
                status: statuses[Status] || 'closed'
              });
            });
          }
        }
      } catch (e) {
        // Try regex extraction as fallback
        const match = text.match(/FR\.TerrainStatusFeed\s*=\s*(\{[\s\S]*?\});/);
        if (match) {
          try {
            const parsed = JSON.parse(match[1]);
            if (parsed.GroomingAreas) {
              parsed.GroomingAreas.forEach(area => {
                (area.Lifts || []).forEach(lift => {
                  lifts.push({
                    name: lift.Name?.trim(),
                    status: statuses[lift.Status] || 'closed'
                  });
                });
              });
            }
          } catch (e2) { /* ignore */ }
        }
      }
    }
  });

  return { lifts, runs };
}

/**
 * Extract using Infosnow (Swiss resorts like Verbier)
 */
async function extractInfosnow(config) {
  const dataUrl = config.dataUrl || 'http://www.infosnow.ch/~apgmontagne/?lang=en&pid=31&tab=web-wi';
  const html = await fetch(dataUrl);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];
  const statusIcons = doc.querySelectorAll('.content table tr .icon[src*="status"]');

  statusIcons.forEach(icon => {
    const src = icon.getAttribute('src') || '';
    const statusMatch = src.match(/([^/]+)\.png$/);
    const status = statusMatch ? normalizeStatus(statusMatch[1]) : 'closed';

    // Name is in the sibling cell
    const row = icon.closest('tr');
    const nameCell = row?.querySelector('td:nth-child(2)');
    const name = nameCell?.textContent?.trim();

    if (name) {
      lifts.push({ name, status });
    }
  });

  return { lifts, runs: [] };
}

/**
 * Extract using SkiWelt pattern (data-state attribute)
 */
async function extractSkiwelt(config) {
  // Use Micado JSON API (discovered via xhr-fetcher)
  const dataUrl = config.dataUrl || 'https://www.skiwelt.at/webapi/micadoweb?api=Micado.Ski.Web/Micado.Ski.Web.IO.Api.FacilityApi/List.api&client=https%3A%2F%2Fsgm.skiwelt.at&lang=en&region=skiwelt&season=winter&typeIDs=1';

  try {
    const json = await fetch(dataUrl);
    const data = JSON.parse(json);

    const lifts = [];

    if (data.items && Array.isArray(data.items)) {
      data.items.forEach(item => {
        const name = item.title;
        const state = (item.state || '').toLowerCase();
        const status = state === 'opened' || state === 'open' ? 'open' :
                       state === 'scheduled' ? 'scheduled' : 'closed';

        if (name) {
          lifts.push({ name, status });
        }
      });
    }

    return { lifts, runs: [] };
  } catch (e) {
    // Fallback to HTML parsing
    const html = await fetch(config.url);
    const dom = new JSDOM(html);
    const doc = dom.window.document;

    const lifts = [];
    const rows = doc.querySelectorAll('div.wrapper > div.row, [data-state]');

    rows.forEach(row => {
      const state = row.getAttribute('data-state');
      const nameEl = row.querySelector('.name, .title') || row.children[2];
      const name = nameEl?.textContent?.trim();

      if (name && state !== null) {
        lifts.push({
          name,
          status: state === '1' ? 'open' : 'closed'
        });
      }
    });

    return { lifts, runs: [] };
  }
}

/**
 * Extract using Kitzbühel pattern - uses Micado JSON API
 */
async function extractKitzski(config) {
  // Use Micado JSON API (discovered via xhr-fetcher)
  const dataUrl = config.dataUrl || 'https://www.kitzski.at/webapi/micadoweb?api=SkigebieteManager/Micado.SkigebieteManager.Plugin.FacilityApi/ListFacilities.api&extensions=o&client=https%3A%2F%2Fsgm.kitzski.at&lang=en&region=kitzski&season=winter&type=lift';

  try {
    const json = await fetch(dataUrl);
    const data = JSON.parse(json);

    const lifts = [];
    const runs = [];

    // Lifts are in facilities array
    if (data.facilities && Array.isArray(data.facilities)) {
      data.facilities.forEach(item => {
        const name = item.title;
        // status: 1=open, 0=closed
        const status = item.status === 1 ? 'open' : 'closed';

        if (name) {
          lifts.push({ name, status });
        }
      });
    }

    return { lifts, runs };
  } catch (e) {
    // Fallback to HTML parsing
    const html = await fetch(config.url);
    const dom = new JSDOM(html);
    const doc = dom.window.document;

    const states = ['?', 'open', 'closed'];
    const lifts = [];
    const items = doc.querySelectorAll('.lifts li[data-locationid] > a, .lift-item, [data-locationid]');

    items.forEach(item => {
      const statusEl = item.querySelector('[class*="status"]') || item.children[0];
      const statusClass = statusEl?.className || '';
      const statusMatch = statusClass.match(/(\d)$/);
      const status = statusMatch ? states[parseInt(statusMatch[1], 10)] || 'closed' : 'closed';

      const nameEl = item.querySelector('.name, .title') || item.children[1];
      const name = nameEl?.textContent?.trim();

      if (name) {
        lifts.push({ name, status });
      }
    });

    return { lifts, runs: [] };
  }
}

/**
 * Extract using Serfaus-Fiss-Ladis pattern
 */
async function extractSerfaus(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];
  const rows = doc.querySelectorAll('#lifte div > table > tbody > tr, .lift-row, table tbody tr');

  rows.forEach(row => {
    const statusEl = row.querySelector('[class*="circle"][class*="status"], .status');
    const statusClass = statusEl?.className || '';
    const statusMatch = statusClass.match(/status-([a-z]+)/);
    const status = statusMatch ? normalizeStatus(statusMatch[1]) : 'closed';

    const nameCell = row.querySelector('td:nth-child(2)') || row.children[1];
    const name = nameCell?.textContent?.trim();

    if (name) {
      lifts.push({ name, status });
    }
  });

  return { lifts, runs: [] };
}

/**
 * Extract using Ski Arlberg pattern (Lech/Zürs, St. Anton)
 * Uses table with aria-label for status
 */
async function extractSkiarlberg(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Try multiple table selectors
  const selectors = [
    '#facility-lifts .table-responsive .table-fixed tbody tr',
    '.facility-table tbody tr',
    'table tbody tr'
  ];

  for (const selector of selectors) {
    const rows = doc.querySelectorAll(selector);
    if (rows.length > 0) {
      rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 2) {
          // Get name from second column
          const name = cells[1]?.textContent?.trim();
          // Get status from first column's aria-label or class
          const statusEl = cells[0]?.querySelector('[aria-label]') || cells[0];
          const ariaLabel = statusEl?.getAttribute('aria-label')?.toLowerCase() || '';
          const className = statusEl?.className?.toLowerCase() || '';

          let status = 'closed';
          if (ariaLabel.includes('open') || ariaLabel.includes('geöffnet') ||
              className.includes('open') || className.includes('green')) {
            status = 'open';
          } else if (ariaLabel.includes('scheduled') || ariaLabel.includes('geplant')) {
            status = 'scheduled';
          }

          if (name && name.length > 0) {
            lifts.push({ name, status });
          }
        }
      });
      break;
    }
  }

  return { lifts, runs: [] };
}

/**
 * Extract using Ischgl pattern - uses Intermaps JSON API
 * Delegates to extractIntermaps with default dataUrl
 */
async function extractIschgl(config) {
  const configWithDefault = {
    ...config,
    dataUrl: config.dataUrl || 'https://winter.intermaps.com/silvretta_arena/data?lang=en'
  };
  return extractIntermaps(configWithDefault);
}

/**
 * Generic Intermaps JSON API extractor
 * Used by Sölden, Saalbach, Portes du Soleil, and other Austrian/European resorts
 * API endpoint format: https://winter.intermaps.com/{resort_id}/data?lang=en
 */
async function extractIntermaps(config) {
  const dataUrl = config.dataUrl;
  if (!dataUrl) return { error: 'No dataUrl specified for Intermaps' };

  try {
    const json = await fetch(dataUrl);
    const data = JSON.parse(json);

    const lifts = [];
    const runs = [];

    // Process lifts - handle "in_preparation" as scheduled
    if (data.lifts && Array.isArray(data.lifts)) {
      data.lifts.forEach(item => {
        const name = item.popup?.title || item.title || item.name;
        const statusText = (item.status || '').toLowerCase();
        const status = statusText === 'open' ? 'open' :
                       (statusText === 'in_preparation' || statusText === 'scheduled') ? 'scheduled' : 'closed';

        if (name) {
          const additionalInfo = item.popup?.['additional-info'] || {};
          const lift = { name, status };

          // Add optional fields if available
          if (item.popup?.subtitle) lift.liftType = item.popup.subtitle;
          if (additionalInfo.capacity) lift.capacity = additionalInfo.capacity;
          if (additionalInfo.length) lift.length = additionalInfo.length;

          lifts.push(lift);
        }
      });
    }

    // Process slopes/runs
    if (data.slopes && Array.isArray(data.slopes)) {
      data.slopes.forEach(item => {
        const name = item.popup?.title || item.title || item.name;
        const statusText = (item.status || '').toLowerCase();
        const status = statusText === 'open' ? 'open' :
                       (statusText === 'in_preparation' || statusText === 'scheduled') ? 'scheduled' : 'closed';

        if (name) {
          runs.push({ name, status });
        }
      });
    }

    return { lifts, runs };
  } catch (e) {
    return { error: e.message };
  }
}

/**
 * Extract using Sölden pattern - uses Intermaps JSON API
 * Delegates to extractIntermaps with default dataUrl and HTML fallback
 */
async function extractSoelden(config) {
  const configWithDefault = {
    ...config,
    dataUrl: config.dataUrl || 'https://winter.intermaps.com/soelden/data?lang=en'
  };

  const result = await extractIntermaps(configWithDefault);

  // If intermaps succeeded, return it
  if (!result.error && result.lifts && result.lifts.length > 0) {
    return result;
  }

  // Fallback to HTML parsing
  try {
    const html = await fetch(config.url);
    const dom = new JSDOM(html);
    const doc = dom.window.document;

    const lifts = [];
    const items = doc.querySelectorAll('[class*="facility-item"], [class*="lift-item"], .status-item');

    items.forEach(item => {
      const nameEl = item.querySelector('[class*="name"], .title, h3, h4');
      const statusEl = item.querySelector('[class*="status"], [class*="state"]');

      const name = nameEl?.textContent?.trim();
      const statusText = statusEl?.textContent?.toLowerCase() || statusEl?.className?.toLowerCase() || '';

      let status = 'closed';
      if (statusText.includes('open') || statusText.includes('geöffnet')) {
        status = 'open';
      }

      if (name) {
        lifts.push({ name, status });
      }
    });

    return { lifts, runs: [] };
  } catch (e) {
    return result; // Return original error if fallback also fails
  }
}

/**
 * Extract using SkiStar pattern (Åre, Trysil, etc.)
 * Note: SkiStar uses a React SPA - needs browser rendering for full data
 */
async function extractSkistar(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Find SimpleView URLs for lift data
  const simpleViewUrls = [];
  const elements = doc.querySelectorAll('[data-url*="SimpleView"]');
  elements.forEach(el => {
    const url = el.getAttribute('data-url');
    if (url && url.includes('SimpleView')) {
      simpleViewUrls.push(url);
    }
  });

  // Fetch and parse each SimpleView
  const baseUrl = new URL(config.url).origin;
  for (const viewUrl of simpleViewUrls) {
    try {
      const viewHtml = await fetch(baseUrl + viewUrl);
      const viewDom = new JSDOM(viewHtml);
      const viewDoc = viewDom.window.document;

      // Parse lift items: .lpv-list__item with .lpv-list__item-name
      const items = viewDoc.querySelectorAll('.lpv-list__item');
      items.forEach(item => {
        const nameEl = item.querySelector('.lpv-list__item-name');
        const statusEl = item.querySelector('.lpv-list__item-status');

        const name = nameEl?.textContent?.trim();
        if (!name) return;

        // Check status class or text
        let status = 'closed';
        if (statusEl?.classList?.contains('lpv-list__item-status--is-open')) {
          status = 'open';
        } else if (statusEl?.textContent?.toLowerCase().includes('open')) {
          status = 'open';
        }

        lifts.push({ name, status });
      });
    } catch (e) {
      // Continue with other views
    }
  }

  if (lifts.length === 0) {
    return { lifts: [], runs: [], note: 'No lift data found in SimpleView' };
  }

  return { lifts, runs: [] };
}

/**
 * Extract using Laax pattern (live.laax.com)
 * Parses server-side rendered HTML with 'widget lift' divs
 */
async function extractLaax(config) {
  // Laax uses server-rendered HTML at live.laax.com/de/anlagen
  const pageUrl = config.dataUrl || 'https://live.laax.com/de/anlagen';

  try {
    const html = await fetch(pageUrl);
    const dom = new JSDOM(html);
    const doc = dom.window.document;

    const lifts = [];

    // Find all lift widgets: <div class="widget lift">
    const liftWidgets = doc.querySelectorAll('.widget.lift');

    liftWidgets.forEach(widget => {
      // Get lift name from the h3 element
      const nameEl = widget.querySelector('.h3, h3');
      const name = nameEl?.textContent?.trim();

      if (!name) return;

      // Get status from the indicator div class
      // Classes: indicator open, indicator closed, indicator in-preparation
      const indicator = widget.querySelector('.indicator');
      const indicatorClass = indicator?.className?.toLowerCase() || '';

      let status = 'closed';
      if (indicatorClass.includes('open')) {
        status = 'open';
      } else if (indicatorClass.includes('in-preparation')) {
        status = 'scheduled';
      }

      lifts.push({ name, status });
    });

    return { lifts, runs: [] };
  } catch (e) {
    return { error: e.message };
  }
}

/**
 * Extract using Livigno pattern
 */
async function extractLivigno(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Livigno uses a table/list format
  const rows = doc.querySelectorAll('.lift-row, .impianto, table tbody tr, [class*="lift-item"]');

  rows.forEach(row => {
    const nameEl = row.querySelector('.name, .lift-name, td:nth-child(1), .title');
    const statusEl = row.querySelector('.status, .stato, td:nth-child(2), [class*="status"]');

    const name = nameEl?.textContent?.trim();
    const statusClass = statusEl?.className?.toLowerCase() || '';
    const statusText = statusEl?.textContent?.toLowerCase() || '';

    let status = 'closed';
    if (statusClass.includes('open') || statusClass.includes('aperto') ||
        statusText.includes('open') || statusText.includes('aperto')) {
      status = 'open';
    }

    if (name) {
      lifts.push({ name, status });
    }
  });

  return { lifts, runs: [] };
}

/**
 * Extract using Perisher pattern (Australia)
 */
async function extractPerisher(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Try multiple selectors
  const rows = doc.querySelectorAll('.lift-status-row, .terrain-row, table tbody tr, [class*="lift"]');

  rows.forEach(row => {
    const nameEl = row.querySelector('.name, .lift-name, td:first-child');
    const statusEl = row.querySelector('.status, [class*="status"], td:last-child');

    const name = nameEl?.textContent?.trim();
    const statusClass = statusEl?.className?.toLowerCase() || '';
    const statusText = statusEl?.textContent?.toLowerCase() || '';

    let status = 'closed';
    if (statusClass.includes('open') || statusText.includes('open')) {
      status = 'open';
    }

    if (name) {
      lifts.push({ name, status });
    }
  });

  return { lifts, runs: [] };
}

/**
 * Extract using Baqueira pattern (Spain)
 */
async function extractBaqueira(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Baqueira uses table format
  const rows = doc.querySelectorAll('table tbody tr, .remonte-row, [class*="lift"]');

  rows.forEach(row => {
    const nameEl = row.querySelector('td:nth-child(1), .name');
    const statusEl = row.querySelector('td:nth-child(2), .status, [class*="estado"]');

    const name = nameEl?.textContent?.trim();
    const statusClass = statusEl?.className?.toLowerCase() || '';
    const statusText = statusEl?.textContent?.toLowerCase() || '';
    const statusImg = statusEl?.querySelector('img')?.getAttribute('src') || '';

    let status = 'closed';
    if (statusClass.includes('open') || statusClass.includes('abierto') ||
        statusText.includes('abierto') || statusImg.includes('green') || statusImg.includes('open')) {
      status = 'open';
    }

    if (name) {
      lifts.push({ name, status });
    }
  });

  return { lifts, runs: [] };
}

/**
 * Extract using Big Sky ReportPal JSON API
 * API: https://www.bigskyresort.com/api/reportpal?resortName=bs&useReportPal=true
 */
async function extractBigsky(config) {
  // Use the ReportPal JSON API
  const apiUrl = config.dataUrl || 'https://www.bigskyresort.com/api/reportpal?resortName=bs&useReportPal=true';
  const response = await fetch(apiUrl);
  const data = JSON.parse(response);

  const lifts = [];
  const runs = [];

  // Extract lifts from facilities.areas.area[].lifts.lift[]
  const facilities = data.facilities || {};
  const areas = facilities.areas?.area || [];

  for (const area of areas) {
    const areaLifts = area.lifts?.lift || [];
    for (const lift of areaLifts) {
      lifts.push({
        name: lift.name,
        status: normalizeStatus(lift.status)
      });
    }

    // Extract trails/runs from facilities.areas.area[].trails.trail[]
    const areaTrails = area.trails?.trail || [];
    for (const trail of areaTrails) {
      runs.push({
        name: trail.name,
        status: normalizeStatus(trail.status),
        difficulty: trail.difficulty
      });
    }
  }

  return { lifts, runs };
}

/**
 * Extract using St. Moritz pattern
 */
async function extractStmoritz(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // St. Moritz uses a table format
  const rows = doc.querySelectorAll('table tbody tr, .lift-row, [class*="bergbahn"]');

  rows.forEach(row => {
    const nameEl = row.querySelector('td:nth-child(1), .name, .title');
    const statusEl = row.querySelector('td:nth-child(2), .status, [class*="status"]');

    const name = nameEl?.textContent?.trim();
    const statusClass = statusEl?.className?.toLowerCase() || '';
    const statusText = statusEl?.textContent?.toLowerCase() || '';

    let status = 'closed';
    if (statusClass.includes('open') || statusClass.includes('offen') ||
        statusText.includes('open') || statusText.includes('offen') || statusText.includes('geöffnet')) {
      status = 'open';
    }

    if (name) {
      lifts.push({ name, status });
    }
  });

  return { lifts, runs: [] };
}

/**
 * Extract using Deer Valley pattern
 */
async function extractDeervalley(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Try to find embedded data
  const scripts = doc.querySelectorAll('script');
  for (const script of scripts) {
    const text = script.textContent || '';
    if (text.includes('chairlift') || text.includes('lift')) {
      // Look for structured data
      const jsonMatch = text.match(/\{[\s\S]*"lifts?"[\s\S]*\}/);
      if (jsonMatch) {
        try {
          const data = JSON.parse(jsonMatch[0]);
          const liftData = data.lifts || [];
          liftData.forEach(lift => {
            lifts.push({
              name: lift.name,
              status: normalizeStatus(lift.status)
            });
          });
        } catch (e) {}
      }
    }
  }

  if (lifts.length === 0) {
    // Fallback to HTML parsing
    const rows = doc.querySelectorAll('.lift-row, .chairlift, table tbody tr');
    rows.forEach(row => {
      const nameEl = row.querySelector('.name, .title, td:first-child');
      const statusEl = row.querySelector('.status, td:last-child');

      const name = nameEl?.textContent?.trim();
      const statusText = statusEl?.textContent?.toLowerCase() || '';

      let status = 'closed';
      if (statusText.includes('open')) {
        status = 'open';
      }

      if (name) {
        lifts.push({ name, status });
      }
    });
  }

  return { lifts, runs: [] };
}

/**
 * Extract using See* network pattern (seelift)
 * See* sites (see2alpes, seeavoriaz, etc.) embed Lumiplan data directly in HTML
 */
async function extractSeelift(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // See* sites use .lift-status-datum elements with Lumiplan images
  const items = doc.querySelectorAll('.lift-status-datum, [class*="lift-status"]');

  items.forEach(item => {
    const nameEl = item.querySelector('.lift-status-datum__name, [class*="name"]');
    const valueEl = item.querySelector('.lift-status-datum__value img, [class*="value"] img');

    const name = nameEl?.textContent?.trim();
    const statusImg = valueEl?.getAttribute('src') || '';

    // Status from Lumiplan image URL: etats/O=open, etats/P=scheduled, etats/F=closed
    let status = 'closed';
    if (statusImg.includes('etats/O') || statusImg.includes('_open')) {
      status = 'open';
    } else if (statusImg.includes('etats/P') || statusImg.includes('_scheduled')) {
      status = 'scheduled';
    }

    if (name) {
      lifts.push({ name, status });
    }
  });

  return { lifts, runs: [] };
}

/**
 * Extract using Saalbach/Skicircus pattern
 * Uses Intermaps JSON API (same as Sölden, Ischgl)
 */
async function extractSaalbach(config) {
  // Use Intermaps JSON API
  const dataUrl = config.dataUrl || 'https://winter.intermaps.com/saalbach_hinterglemm_leogang_fieberbrunn/data?lang=en';

  try {
    const json = await fetch(dataUrl);
    const data = JSON.parse(json);

    const lifts = [];
    const runs = [];

    // Process lifts
    if (data.lifts && Array.isArray(data.lifts)) {
      data.lifts.forEach(item => {
        const name = item.popup?.title || item.title || item.name;
        const statusText = (item.status || '').toLowerCase();
        const status = statusText === 'open' ? 'open' :
                       statusText === 'scheduled' ? 'scheduled' : 'closed';

        if (name) {
          lifts.push({ name, status });
        }
      });
    }

    // Process slopes/runs
    if (data.slopes && Array.isArray(data.slopes)) {
      data.slopes.forEach(item => {
        const name = item.popup?.title || item.title || item.name;
        const statusText = (item.status || '').toLowerCase();
        const status = statusText === 'open' ? 'open' :
                       statusText === 'scheduled' ? 'scheduled' : 'closed';

        if (name) {
          runs.push({ name, status });
        }
      });
    }

    return { lifts, runs };
  } catch (e) {
    return { error: e.message };
  }
}

/**
 * Extract using Davos pattern (Vue.js SPA with API)
 */
async function extractDavos(config) {
  // Davos uses a Vue.js SPA that fetches data from an API
  // Try to find the API endpoint or parse pre-rendered content
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Look for data in script tags
  const scripts = doc.querySelectorAll('script');
  for (const script of scripts) {
    const text = script.textContent || '';
    if (text.includes('lifts') || text.includes('anlagen')) {
      try {
        const jsonMatch = text.match(/\{[\s\S]*"lifts?"[\s\S]*\}/);
        if (jsonMatch) {
          const data = JSON.parse(jsonMatch[0]);
          (data.lifts || []).forEach(lift => {
            lifts.push({
              name: lift.name || lift.title,
              status: normalizeStatus(lift.status)
            });
          });
        }
      } catch (e) {}
    }
  }

  // Fallback to HTML parsing
  if (lifts.length === 0) {
    const items = doc.querySelectorAll('.lift-item, [class*="anlage"], tr');
    items.forEach(item => {
      const nameEl = item.querySelector('.name, .title, td:nth-child(1)');
      const statusEl = item.querySelector('.status, td:nth-child(2)');

      const name = nameEl?.textContent?.trim();
      const statusText = statusEl?.textContent?.toLowerCase() || '';

      let status = 'closed';
      if (statusText.includes('open') || statusText.includes('offen') || statusText.includes('in betrieb')) {
        status = 'open';
      }

      if (name) {
        lifts.push({ name, status });
      }
    });
  }

  return { lifts, runs: [] };
}

/**
 * Extract using Websenso API (used by French resorts like Serre-Chevalier)
 * API returns HTML snippets with embedded lift/slope data
 */
async function extractWebsenso(config) {
  const websiteKey = config.websensoKey || config.id.replace(/-/g, '') + '.com';
  const apiUrl = `https://api.websenso.com/api/snowreport/onecall/${websiteKey}`;

  // Build request body to fetch lift clusters
  const requestBody = {
    data: {
      clusters: {
        lifts: {
          clusterType: 'poi-type',
          filterBy: JSON.stringify({ category: 'lifts' }),
          sortBy: JSON.stringify({ name: 'ASC' })
        },
        slopes: {
          clusterType: 'poi-difficulty',
          filterBy: JSON.stringify({ category: 'slopes', type: 'alpine' }),
          sortBy: JSON.stringify({ difficultyWeight: 'ASC', name: 'ASC' })
        }
      }
    }
  };

  try {
    const response = await fetchPost(apiUrl, requestBody);
    const data = JSON.parse(response);
    const lifts = [];
    const runs = [];

    // Parse lift clusters from HTML snippets
    const content = data.content || {};
    for (const [key, html] of Object.entries(content)) {
      if (typeof html !== 'string') continue;

      // Extract individual items from HTML
      // Format: <dl class="ws-snowreport--name">...<dd class="value">NAME</dd></dl>
      // Status is in: <dl class="ws-snowreport--status" data-status="open|closed">
      const nameMatches = html.matchAll(/<dl class="ws-snowreport--name"[^>]*>.*?<dd class="value">([^<]+)<\/dd>/gs);
      const statusMatches = html.matchAll(/data-status="([^"]+)"/g);
      const typeMatches = html.matchAll(/data-poi-type="([^"]+)"/g);

      const names = [...nameMatches].map(m => m[1].trim());
      const statuses = [...statusMatches].map(m => m[1].toLowerCase());
      const types = [...typeMatches].map(m => m[1]);

      // Determine if this is lifts or slopes based on types
      const isLift = types.some(t => ['TC', 'TSD', 'TSDB', 'TS', 'TK', 'TR', 'FUN', 'TPH', 'DMC', 'TM'].includes(t));

      for (let i = 0; i < names.length; i++) {
        const name = names[i];
        const status = statuses[i] === 'open' ? 'open' : 'closed';

        if (isLift) {
          lifts.push({ name, status });
        } else {
          runs.push({ name, status });
        }
      }
    }

    return { lifts, runs };
  } catch (e) {
    return { error: e.message };
  }
}

/**
 * Extract using GrandValira pattern (Drupal with embedded JSON)
 */
async function extractGrandvalira(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // GrandValira embeds data in Drupal's ajaxPageState or similar
  const scripts = doc.querySelectorAll('script');
  for (const script of scripts) {
    const text = script.textContent || '';
    if (text.includes('facilities') || text.includes('lifts')) {
      try {
        const matches = text.match(/\{[\s\S]*?\}/g) || [];
        for (const match of matches) {
          try {
            const data = JSON.parse(match);
            if (data.facilities || data.lifts) {
              (data.facilities || data.lifts || []).forEach(item => {
                lifts.push({
                  name: item.name || item.title,
                  status: normalizeStatus(item.status || item.state)
                });
              });
            }
          } catch (e) {}
        }
      } catch (e) {}
    }
  }

  // Fallback to HTML parsing - look for sectors with lifts
  if (lifts.length === 0) {
    const items = doc.querySelectorAll('[class*="sector"] li, [class*="lift"], .facility-item');
    items.forEach(item => {
      const nameEl = item.querySelector('h3, .name, strong');
      const statusClass = item.className?.toLowerCase() || '';
      const statusText = item.textContent?.toLowerCase() || '';

      const name = nameEl?.textContent?.trim();

      let status = 'closed';
      if (statusClass.includes('open') || statusText.includes('opened') || statusText.includes('enabled')) {
        status = 'open';
      }

      if (name) {
        lifts.push({ name, status });
      }
    });
  }

  return { lifts, runs: [] };
}

/**
 * Extract using Mayrhofen pattern
 */
async function extractMayrhofen(config) {
  // Use Intermaps JSON API (discovered via xhr-fetcher - same as Sölden)
  const dataUrl = config.dataUrl || 'https://winter.intermaps.com/mayrhofen/data?lang=en';

  try {
    const json = await fetch(dataUrl);
    const data = JSON.parse(json);

    const lifts = [];
    const runs = [];

    // Process lifts
    if (data.lifts && Array.isArray(data.lifts)) {
      data.lifts.forEach(item => {
        const name = item.popup?.title || item.title || item.name;
        const statusText = (item.status || '').toLowerCase();
        const status = statusText === 'open' ? 'open' :
                       statusText === 'scheduled' ? 'scheduled' : 'closed';

        if (name) {
          lifts.push({ name, status });
        }
      });
    }

    // Process slopes/runs
    if (data.slopes && Array.isArray(data.slopes)) {
      data.slopes.forEach(item => {
        const name = item.popup?.title || item.title || item.name;
        const statusText = (item.status || '').toLowerCase();
        const status = statusText === 'open' ? 'open' :
                       statusText === 'scheduled' ? 'scheduled' : 'closed';

        if (name) {
          runs.push({ name, status });
        }
      });
    }

    return { lifts, runs };
  } catch (e) {
    // Fallback to HTML parsing
    const html = await fetch(config.url);
    const dom = new JSDOM(html);
    const doc = dom.window.document;

    const lifts = [];
    const rows = doc.querySelectorAll('table tbody tr, .lift-row, [class*="bergbahn"]');

    rows.forEach(row => {
      const nameEl = row.querySelector('td:nth-child(1), .name, .title');
      const statusEl = row.querySelector('td:nth-child(2), .status, [class*="status"]');

      const name = nameEl?.textContent?.trim();
      const statusClass = statusEl?.className?.toLowerCase() || '';
      const statusText = statusEl?.textContent?.toLowerCase() || '';

      let status = 'closed';
      if (statusClass.includes('open') || statusClass.includes('green') ||
          statusText.includes('open') || statusText.includes('geöffnet') || statusText.includes('in betrieb')) {
        status = 'open';
      }

      if (name) {
        lifts.push({ name, status });
      }
    });

    return { lifts, runs: [] };
  }
}

/**
 * Extract using Czech Skiresort.cz pattern
 */
async function extractSkiresortcz(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Czech site uses table with lift info
  const rows = doc.querySelectorAll('table tr');

  rows.forEach(row => {
    const cells = row.querySelectorAll('td');
    if (cells.length >= 2) {
      const name = cells[1]?.textContent?.trim();
      const statusCell = cells[0];
      const statusImg = statusCell?.querySelector('img');
      const statusSrc = statusImg?.getAttribute('src') || '';

      let status = 'closed';
      if (statusSrc.includes('green') || statusSrc.includes('open')) {
        status = 'open';
      }

      if (name) {
        lifts.push({ name, status });
      }
    }
  });

  return { lifts, runs: [] };
}

/**
 * Extract using Zugspitze pattern (React-based structured list)
 */
async function extractZugspitze(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Look for facility items with status badges
  const items = doc.querySelectorAll('[class*="facility"], [class*="lift"], .status-item, li');

  items.forEach(item => {
    const text = item.textContent || '';

    // Pattern: "Cable car Zugspitze" with status nearby
    if (text.includes('cable car') || text.includes('lift') || text.includes('Bahn') || text.includes('Sessellift')) {
      const nameMatch = text.match(/(cable car|lift|bahn|Sessellift)[^–\n]*/i);
      if (nameMatch) {
        const name = nameMatch[0].trim();
        const statusText = text.toLowerCase();

        let status = 'closed';
        if (statusText.includes('open') || statusText.includes('geöffnet') || !statusText.includes('closed')) {
          // Check for explicit closed indicators
          if (!statusText.includes('closed') && !statusText.includes('geschlossen')) {
            status = 'open';
          }
        }

        if (name && name.length > 3) {
          lifts.push({ name, status });
        }
      }
    }
  });

  // Fallback to table parsing
  if (lifts.length === 0) {
    const rows = doc.querySelectorAll('table tbody tr');
    rows.forEach(row => {
      const cells = row.querySelectorAll('td');
      if (cells.length >= 2) {
        const name = cells[0]?.textContent?.trim();
        const statusCell = cells[cells.length - 1];
        const statusText = statusCell?.textContent?.toLowerCase() || '';

        let status = 'closed';
        if (statusText.includes('open') || statusText.includes('geöffnet')) {
          status = 'open';
        }

        if (name) {
          lifts.push({ name, status });
        }
      }
    });
  }

  return { lifts, runs: [] };
}

/**
 * Extract using Snow Space Salzburg pattern
 */
async function extractSnowspace(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Snow Space uses icons for lift types and status indicators
  const items = doc.querySelectorAll('.lift-item, [class*="lift-status"], tr');

  items.forEach(item => {
    const nameEl = item.querySelector('.name, .title, td:nth-child(2)');
    const statusEl = item.querySelector('.status, [class*="status"], td:nth-child(1)');

    const name = nameEl?.textContent?.trim();
    const statusClass = statusEl?.className?.toLowerCase() || '';

    let status = 'closed';
    if (statusClass.includes('open') || statusClass.includes('green') || statusClass.includes('active')) {
      status = 'open';
    }

    if (name) {
      lifts.push({ name, status });
    }
  });

  return { lifts, runs: [] };
}

/**
 * Extract using Aletsch Arena pattern
 */
async function extractAletsch(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Look for lift status items
  const items = doc.querySelectorAll('.lift-item, [class*="anlage"], table tbody tr, li');

  items.forEach(item => {
    const nameEl = item.querySelector('.name, .title, td:nth-child(1), strong');
    const statusEl = item.querySelector('.status, [class*="status"], td:nth-child(2)');

    const name = nameEl?.textContent?.trim();
    const statusClass = statusEl?.className?.toLowerCase() || '';
    const statusText = statusEl?.textContent?.toLowerCase() || item.textContent?.toLowerCase() || '';

    let status = 'closed';
    if (statusClass.includes('open') || statusClass.includes('green') ||
        statusText.includes('open') || statusText.includes('offen') || statusText.includes('geöffnet')) {
      status = 'open';
    }

    if (name && name.length > 2) {
      lifts.push({ name, status });
    }
  });

  return { lifts, runs: [] };
}

/**
 * Extract using Vars/Risoul pattern
 */
async function extractVars(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Look for lift status in snow bulletin format
  const items = doc.querySelectorAll('.lift-row, table tbody tr, li[class*="lift"]');

  items.forEach(item => {
    const nameEl = item.querySelector('.name, td:nth-child(1), strong');
    const statusEl = item.querySelector('.status, td:nth-child(2), [class*="status"]');

    const name = nameEl?.textContent?.trim();
    const statusText = statusEl?.textContent?.toLowerCase() || '';
    const statusImg = statusEl?.querySelector('img')?.getAttribute('src') || '';

    let status = 'closed';
    if (statusText.includes('open') || statusText.includes('ouvert') ||
        statusImg.includes('green') || statusImg.includes('open')) {
      status = 'open';
    }

    if (name) {
      lifts.push({ name, status });
    }
  });

  return { lifts, runs: [] };
}

/**
 * Extract using Silvretta Montafon pattern
 */
async function extractMontafon(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Look for lift status items
  const items = doc.querySelectorAll('.lift-item, [class*="facility"], table tbody tr');

  items.forEach(item => {
    const nameEl = item.querySelector('.name, .title, td:nth-child(1)');
    const statusEl = item.querySelector('.status, [class*="status"], td:nth-child(2)');

    const name = nameEl?.textContent?.trim();
    const statusClass = statusEl?.className?.toLowerCase() || '';
    const statusText = statusEl?.textContent?.toLowerCase() || '';

    let status = 'closed';
    if (statusClass.includes('open') || statusClass.includes('green') ||
        statusText.includes('open') || statusText.includes('geöffnet')) {
      status = 'open';
    }

    if (name) {
      lifts.push({ name, status });
    }
  });

  return { lifts, runs: [] };
}

/**
 * Extract using Arosa Lenzerheide pattern
 */
async function extractArosa(config) {
  return await extractDavos(config);  // Similar Vue.js pattern
}

/**
 * Extract using Zillertal Arena pattern
 */
async function extractZillertal(config) {
  return await extractMayrhofen(config);  // Similar Austrian pattern
}

/**
 * Extract using Wendelstein pattern
 */
async function extractWendelstein(config) {
  return await extractZugspitze(config);  // Similar German pattern
}

/**
 * Extract using Folgaria/Alpe Cimbra pattern
 */
async function extractFolgaria(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Italian resort - look for impianti (lifts)
  const items = doc.querySelectorAll('[class*="impianto"], [class*="lift"], table tbody tr');

  items.forEach(item => {
    const nameEl = item.querySelector('.name, .title, td:nth-child(1)');
    const statusEl = item.querySelector('.status, [class*="stato"], td:nth-child(2)');

    const name = nameEl?.textContent?.trim();
    const statusClass = statusEl?.className?.toLowerCase() || '';
    const statusText = statusEl?.textContent?.toLowerCase() || '';

    let status = 'closed';
    if (statusClass.includes('open') || statusClass.includes('aperto') ||
        statusText.includes('open') || statusText.includes('aperto')) {
      status = 'open';
    }

    if (name) {
      lifts.push({ name, status });
    }
  });

  return { lifts, runs: [] };
}

/**
 * Generic extraction - tries multiple strategies
 */
async function extractGeneric(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Strategy 1: Look for embedded JSON data
  const scripts = doc.querySelectorAll('script');
  for (const script of scripts) {
    const text = script.textContent || '';
    // Check for common data patterns
    if (text.includes('lifts') || text.includes('facilities') || text.includes('status')) {
      const patterns = [
        /"lifts"\s*:\s*\[([\s\S]*?)\]/,
        /"facilities"\s*:\s*\[([\s\S]*?)\]/,
        /liftStatus\s*=\s*(\{[\s\S]*?\})/
      ];

      for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match) {
          try {
            const data = JSON.parse(`[${match[1]}]`);
            data.forEach(item => {
              if (item.name || item.title) {
                lifts.push({
                  name: item.name || item.title,
                  status: normalizeStatus(item.status || item.state)
                });
              }
            });
          } catch (e) {}
        }
      }
    }
  }

  // Strategy 2: Try common table selectors
  if (lifts.length === 0) {
    const tableSelectors = [
      'table tbody tr',
      '.lift-row',
      '.facility-row',
      '[class*="lift-item"]',
      '[class*="status-row"]'
    ];

    for (const selector of tableSelectors) {
      const rows = doc.querySelectorAll(selector);
      if (rows.length > 0) {
        rows.forEach(row => {
          const cells = row.querySelectorAll('td');
          if (cells.length >= 2) {
            const name = cells[0]?.textContent?.trim() || cells[1]?.textContent?.trim();
            const statusCell = cells[cells.length - 1];
            const statusClass = statusCell?.className?.toLowerCase() || '';
            const statusText = statusCell?.textContent?.toLowerCase() || '';

            let status = 'closed';
            if (statusClass.includes('open') || statusClass.includes('green') ||
                statusText.includes('open') || statusText.includes('offen') ||
                statusText.includes('ouvert') || statusText.includes('aperto')) {
              status = 'open';
            }

            if (name && name.length > 1 && name.length < 100) {
              lifts.push({ name, status });
            }
          }
        });
        break;
      }
    }
  }

  if (lifts.length === 0) {
    return { lifts: [], runs: [], note: 'No lift data found - may require browser rendering or custom extractor' };
  }

  return { lifts, runs: [] };
}

/**
 * Main extraction function
 */
async function extractResort(resortId) {
  const resort = resorts.find(r => r.id === resortId);
  if (!resort) {
    return { error: `Resort not found: ${resortId}` };
  }

  // Check if resort requires browser rendering (not supported)
  if (resort.requiresBrowserRendering) {
    return {
      lifts: [],
      runs: [],
      requiresBrowserRendering: true,
      note: 'Requires JavaScript rendering (not currently supported)'
    };
  }

  // Logging moved to runAll() for batched output

  try {
    switch (resort.platform) {
      case 'lumiplan':
        return await extractLumiplan(resort);
      case 'skiplanxml':
        return await extractSkiplanXml(resort);
      case 'nuxt':
        return await extractNuxt(resort);
      case 'dolomiti':
        return await extractDolomiti(resort);
      case 'skiplan':
        return await extractSkiplan(resort);
      case 'vail':
        return await extractVail(resort);
      case 'infosnow':
        return await extractInfosnow(resort);
      case 'skiwelt':
        return await extractSkiwelt(resort);
      case 'kitzski':
        return await extractKitzski(resort);
      case 'serfaus':
        return await extractSerfaus(resort);
      case 'skiarlberg':
        return await extractSkiarlberg(resort);
      case 'ischgl':
        return await extractIschgl(resort);
      case 'soelden':
        return await extractSoelden(resort);
      case 'intermaps':
        return await extractIntermaps(resort);
      case 'skistar':
        return await extractSkistar(resort);
      case 'laax':
        return await extractLaax(resort);
      case 'livigno':
        return await extractLivigno(resort);
      case 'perisher':
        return await extractPerisher(resort);
      case 'baqueira':
        return await extractBaqueira(resort);
      case 'bigsky':
        return await extractBigsky(resort);
      case 'stmoritz':
        return await extractStmoritz(resort);
      case 'deervalley':
        return await extractDeervalley(resort);
      case 'seelift':
        return await extractSeelift(resort);
      case 'saalbach':
        return await extractSaalbach(resort);
      case 'davos':
        return await extractDavos(resort);
      case 'grandvalira':
        return await extractGrandvalira(resort);
      case 'websenso':
        return await extractWebsenso(resort);
      case 'mayrhofen':
        return await extractMayrhofen(resort);
      case 'skiresortcz':
        return await extractSkiresortcz(resort);
      case 'zugspitze':
        return await extractZugspitze(resort);
      case 'snowspace':
        return await extractSnowspace(resort);
      case 'aletsch':
        return await extractAletsch(resort);
      case 'vars':
        return await extractVars(resort);
      case 'montafon':
        return await extractMontafon(resort);
      case 'arosa':
        return await extractArosa(resort);
      case 'zillertal':
        return await extractZillertal(resort);
      case 'wendelstein':
        return await extractWendelstein(resort);
      case 'folgaria':
        return await extractFolgaria(resort);
      case 'custom':
        // Try generic extraction for custom resorts
        return await extractGeneric(resort);
      default:
        return { error: `Unknown platform: ${resort.platform}` };
    }
  } catch (e) {
    return { error: e.message };
  }
}

/**
 * Run all resorts and generate report with parallel execution
 */
async function runAll() {
  const results = {};
  const total = resorts.length;
  const startTime = Date.now();
  let completed = 0;

  console.log(`Starting parallel extraction of ${total} resorts (concurrency: ${CONCURRENCY_LIMIT})\n`);

  // Process in batches for controlled concurrency
  for (let i = 0; i < resorts.length; i += CONCURRENCY_LIMIT) {
    const batch = resorts.slice(i, i + CONCURRENCY_LIMIT);
    const batchNum = Math.floor(i / CONCURRENCY_LIMIT) + 1;
    const totalBatches = Math.ceil(resorts.length / CONCURRENCY_LIMIT);

    console.log(`\n--- Batch ${batchNum}/${totalBatches} (resorts ${i + 1}-${Math.min(i + CONCURRENCY_LIMIT, total)}) ---`);

    // Print "starting" messages immediately (unbatched) so user sees activity
    for (const resort of batch) {
      process.stdout.write(`  → Testing ${resort.name}...\n`);
    }

    // Run batch in parallel and collect results
    const batchResults = await Promise.all(
      batch.map(async (resort, batchIndex) => {
        const resortStartTime = Date.now();
        try {
          const result = await extractResort(resort.id);
          return { resort, result, duration: Date.now() - resortStartTime };
        } catch (e) {
          return { resort, result: { error: e.message }, duration: Date.now() - resortStartTime };
        }
      })
    );

    // Print grouped results after batch completes
    console.log('');  // Blank line before results
    for (const { resort, result, duration } of batchResults) {
      completed++;
      results[resort.id] = {
        name: resort.name,
        platform: resort.platform,
        openskimap_id: resort.openskimap_id,
        ...result
      };

      const status = result.error
        ? `❌ Error: ${result.error}`
        : result.note
          ? `⚠️  ${result.note}`
          : `✓ Lifts: ${result.lifts?.length || 0}, Runs: ${result.runs?.length || 0}`;

      console.log(`  [${completed}/${total}] ${resort.name} (${duration}ms) - ${status}`);
    }
  }

  const totalTime = ((Date.now() - startTime) / 1000).toFixed(1);
  console.log(`\nCompleted in ${totalTime}s`);

  return results;
}

// Try to load name mapper (optional - for OpenSkiMap integration)
let nameMapper = null;
try {
  nameMapper = require('./name_mapper.js');
} catch (e) {
  console.warn('Name mapper not available - OpenSkiMap mapping disabled');
}

/**
 * Extract and map resort data to OpenSkiMap
 */
async function extractAndMap(resortId) {
  const resort = resorts.find(r => r.id === resortId);
  if (!resort) {
    return { error: `Resort not found: ${resortId}` };
  }

  const extracted = await extractResort(resortId);

  if (extracted.error || !nameMapper) {
    return extracted;
  }

  // Map to OpenSkiMap
  const mapped = nameMapper.mapResortToOpenSkiMap(resort.openskimap_id, extracted);

  return {
    ...extracted,
    openskimap: mapped.summary,
    mappedLifts: mapped.lifts.mapped,
    mappedRuns: mapped.runs.mapped,
    unmappedLifts: mapped.lifts.unmapped,
    unmappedRuns: mapped.runs.unmapped
  };
}

// Export for use as module
module.exports = {
  extractResort,
  extractAndMap,
  runAll,
  resorts
};

// Run if executed directly
if (require.main === module) {
  const arg = process.argv[2];
  const withMapping = process.argv.includes('--map');

  if (arg === '--all') {
    runAll().then(results => {
      console.log('\n\n=== SUMMARY ===');

      // Categorize results
      const browserRenderingRequired = Object.values(results).filter(r => r.requiresBrowserRendering);
      const successful = Object.values(results).filter(r => !r.error && !r.note && !r.requiresBrowserRendering);
      const failed = Object.values(results).filter(r => r.error);

      console.log(`Successful: ${successful.length}/${Object.keys(results).length}`);
      console.log(`Requires browser rendering (skipped): ${browserRenderingRequired.length}`);
      if (failed.length > 0) {
        console.log(`Errors: ${failed.length}`);
      }

      // Check for insufficient data (≤2 lifts AND ≤2 runs) - exclude browser rendering resorts
      const insufficientData = Object.entries(results).filter(([id, r]) => {
        if (r.error || r.note || r.requiresBrowserRendering) return false;
        const liftCount = r.lifts?.length || 0;
        const runCount = r.runs?.length || 0;
        return liftCount <= 2 && runCount <= 2;
      });

      if (insufficientData.length > 0) {
        console.log(`\n⚠️  Resorts with insufficient data (≤2 lifts AND ≤2 runs): ${insufficientData.length}`);
        insufficientData.forEach(([id, r]) => {
          console.log(`  - ${r.name}: ${r.lifts?.length || 0} lifts, ${r.runs?.length || 0} runs`);
        });
      }

      console.log('\nBy platform:');
      const byPlatform = {};
      Object.values(results).forEach(r => {
        byPlatform[r.platform] = byPlatform[r.platform] || { total: 0, success: 0, browserRendering: 0 };
        byPlatform[r.platform].total++;
        if (r.requiresBrowserRendering) {
          byPlatform[r.platform].browserRendering++;
        } else if (!r.error && !r.note) {
          byPlatform[r.platform].success++;
        }
      });
      Object.entries(byPlatform).forEach(([p, s]) => {
        const suffix = s.browserRendering > 0 ? ` (${s.browserRendering} require JS)` : '';
        console.log(`  ${p}: ${s.success}/${s.total}${suffix}`);
      });

      // Exit with error code if there are insufficient data resorts (excluding browser rendering ones)
      if (insufficientData.length > 0) {
        console.log('\n❌ FAILED: Some resorts have insufficient data');
        process.exit(1);
      }
    });
  } else if (arg && arg !== '--map') {
    const fn = withMapping ? extractAndMap : extractResort;
    fn(arg).then(result => {
      console.log(JSON.stringify(result, null, 2));
    });
  } else {
    console.log('Usage: node runner.js [resort-id | --all] [--map]');
    console.log('\nOptions:');
    console.log('  --map    Include OpenSkiMap name mapping');
    console.log('\nAvailable resorts:');
    resorts.forEach(r => console.log(`  ${r.id} - ${r.name} (${r.platform})`));
  }
}
