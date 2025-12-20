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

// Load configs
const resorts = require('./resorts.json').resorts;

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
 * Extract using Lumiplan bulletin
 */
async function extractLumiplan(config) {
  const dataUrl = config.dataUrl;
  if (!dataUrl) return { error: 'No dataUrl specified' };

  const html = await fetch(dataUrl);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];
  const runs = [];

  // New Lumiplan format uses POI_info elements
  const items = doc.querySelectorAll('.POI_info');
  items.forEach(item => {
    const nameEl = item.querySelector('span.nom');
    const statusImg = item.querySelector('img.img_status[src*="etats"]');
    const typeImg = item.querySelector('img.img_type');

    if (nameEl) {
      const name = nameEl.textContent.trim().replace(/\.$/, ''); // Remove trailing dot
      const src = statusImg?.getAttribute('src') || '';
      const typeSrc = typeImg?.getAttribute('src') || '';

      // Parse status from image filename (e.g., lp_runway_trail_open.svg, lp_runway_trail_scheduled.svg)
      let status = 'closed';
      if (src.includes('_open')) status = 'open';
      else if (src.includes('_scheduled')) status = 'scheduled';
      else if (src.includes('_closed')) status = 'closed';

      // Determine if lift or run based on type image
      const isLift = typeSrc.includes('CHAIRLIFT') || typeSrc.includes('GONDOLA') ||
                     typeSrc.includes('CABLE') || typeSrc.includes('DRAG') ||
                     typeSrc.includes('FUNICULAR') || typeSrc.includes('LIFT');

      if (name) {
        if (isLift) {
          lifts.push({ name, status });
        } else {
          runs.push({ name, status });
        }
      }
    }
  });

  // Fallback: try old prl_group format
  if (lifts.length === 0 && runs.length === 0) {
    const groups = doc.querySelectorAll('.prl_group');
    groups.forEach(group => {
      const nameEl = group.querySelector('.prl_nm');
      const statusEl = group.querySelector('img[src*=".svg"]');

      if (nameEl && statusEl) {
        const name = nameEl.textContent.trim();
        const src = statusEl.getAttribute('src') || '';
        const statusMatch = src.match(/([OFP])\.svg$/);
        const status = statusMatch ? {
          'O': 'open',
          'P': 'scheduled',
          'F': 'closed'
        }[statusMatch[1]] || 'closed' : 'closed';

        lifts.push({ name, status });
      }
    });
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

  // Find script containing TerrainStatusFeed
  const scripts = doc.querySelectorAll('script');
  let feedData = null;

  scripts.forEach(script => {
    const text = script.textContent || '';
    if (text.includes('TerrainStatusFeed = {')) {
      try {
        const context = { FR: {} };
        vm.runInNewContext(text, context);
        feedData = context.FR?.TerrainStatusFeed?.Lifts || [];
      } catch (e) {
        // Try alternative extraction
        const match = text.match(/TerrainStatusFeed\s*=\s*(\{[\s\S]*?\});/);
        if (match) {
          try {
            const jsonStr = match[1].replace(/'/g, '"');
            const parsed = JSON.parse(jsonStr);
            feedData = parsed.Lifts || [];
          } catch (e2) { /* ignore */ }
        }
      }
    }
  });

  if (feedData) {
    feedData.forEach(({ Name, Status }) => {
      lifts.push({
        name: Name?.trim(),
        status: statuses[Status] || 'closed'
      });
    });
  }

  return { lifts, runs: [] };
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

/**
 * Extract using Kitzbühel pattern
 */
async function extractKitzski(config) {
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
 * Extract using Ischgl pattern
 */
async function extractIschgl(config) {
  return await extractSkiarlberg(config);  // Same pattern
}

/**
 * Extract using Sölden pattern
 */
async function extractSoelden(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Look for lift status elements
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
 */
async function extractLaax(config) {
  // Laax uses a separate API at live.laax.com
  const apiUrl = 'https://live.laax.com/api/lifts';
  try {
    const data = await fetch(apiUrl);
    const json = JSON.parse(data);

    const lifts = [];
    if (Array.isArray(json)) {
      json.forEach(lift => {
        lifts.push({
          name: lift.name || lift.title,
          status: normalizeStatus(lift.status || lift.state)
        });
      });
    }

    return { lifts, runs: [] };
  } catch (e) {
    // Fallback to HTML parsing
    const html = await fetch(config.url);
    const dom = new JSDOM(html);
    const doc = dom.window.document;

    const lifts = [];
    const rows = doc.querySelectorAll('.lift-item, .facility-row, tr[data-lift]');

    rows.forEach(row => {
      const nameEl = row.querySelector('.name, .title, td:nth-child(1)');
      const statusEl = row.querySelector('.status, .state, td:nth-child(2)');

      const name = nameEl?.textContent?.trim();
      const statusText = statusEl?.textContent?.toLowerCase() || '';

      let status = 'closed';
      if (statusText.includes('open') || statusText.includes('offen')) {
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
 * Extract using Big Sky pattern
 */
async function extractBigsky(config) {
  const html = await fetch(config.url);
  const dom = new JSDOM(html);
  const doc = dom.window.document;

  const lifts = [];

  // Try to find embedded JSON data first
  const scripts = doc.querySelectorAll('script');
  for (const script of scripts) {
    const text = script.textContent || '';
    if (text.includes('liftStatus') || text.includes('terrainStatus')) {
      const jsonMatch = text.match(/\{[\s\S]*"lifts?"[\s\S]*\}/);
      if (jsonMatch) {
        try {
          const data = JSON.parse(jsonMatch[0]);
          const liftData = data.lifts || data.liftStatus || [];
          liftData.forEach(lift => {
            lifts.push({
              name: lift.name || lift.liftName,
              status: normalizeStatus(lift.status)
            });
          });
        } catch (e) {}
      }
    }
  }

  if (lifts.length === 0) {
    // Fallback to table parsing
    const rows = doc.querySelectorAll('.lift-row, table tbody tr');
    rows.forEach(row => {
      const nameEl = row.querySelector('.name, td:first-child');
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

  console.log(`Extracting: ${resort.name} (${resort.platform})`);

  try {
    switch (resort.platform) {
      case 'lumiplan':
        return await extractLumiplan(resort);
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
 * Run a batch of resorts in parallel
 */
async function runBatch(batch, startIndex, total) {
  const results = await Promise.all(
    batch.map(async (resort, i) => {
      const index = startIndex + i + 1;
      const startTime = Date.now();
      const result = await extractResort(resort.id);
      const duration = Date.now() - startTime;

      return {
        resort,
        result,
        index,
        duration
      };
    })
  );

  return results;
}

/**
 * Run all resorts and generate report with parallel execution
 */
async function runAll() {
  const results = {};
  const total = resorts.length;
  const startTime = Date.now();

  console.log(`Starting parallel extraction of ${total} resorts (concurrency: ${CONCURRENCY_LIMIT})\n`);

  // Process in batches for controlled concurrency
  for (let i = 0; i < resorts.length; i += CONCURRENCY_LIMIT) {
    const batch = resorts.slice(i, i + CONCURRENCY_LIMIT);
    const batchNum = Math.floor(i / CONCURRENCY_LIMIT) + 1;
    const totalBatches = Math.ceil(resorts.length / CONCURRENCY_LIMIT);

    console.log(`\n--- Batch ${batchNum}/${totalBatches} (resorts ${i + 1}-${Math.min(i + CONCURRENCY_LIMIT, total)}) ---`);

    const batchResults = await runBatch(batch, i, total);

    // Process results and print grouped logs
    for (const { resort, result, index, duration } of batchResults) {
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

      console.log(`[${index}/${total}] ${resort.name} (${duration}ms) - ${status}`);
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
      const successful = Object.values(results).filter(r => !r.error && !r.note);
      console.log(`Successful: ${successful.length}/${Object.keys(results).length}`);

      console.log('\nBy platform:');
      const byPlatform = {};
      Object.values(results).forEach(r => {
        byPlatform[r.platform] = byPlatform[r.platform] || { total: 0, success: 0 };
        byPlatform[r.platform].total++;
        if (!r.error && !r.note) byPlatform[r.platform].success++;
      });
      Object.entries(byPlatform).forEach(([p, s]) => {
        console.log(`  ${p}: ${s.success}/${s.total}`);
      });
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
