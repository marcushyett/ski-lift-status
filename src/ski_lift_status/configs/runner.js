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

/**
 * Fetch URL content
 */
async function fetch(url) {
  return new Promise((resolve, reject) => {
    const protocol = url.startsWith('https') ? https : http;
    const agent = getProxyAgent(url);

    const options = {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; SkiLiftStatus/1.0)',
        'Accept': 'text/html,application/json'
      }
    };

    if (agent) {
      options.agent = agent;
    }

    protocol.get(url, options, (res) => {
      // Handle redirects
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return fetch(res.headers.location).then(resolve).catch(reject);
      }

      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data));
    }).on('error', reject);
  });
}

/**
 * Extract __NUXT__ data from HTML
 */
function extractNuxtData(html) {
  const match = html.match(/window\.__NUXT__\s*=\s*(\(function[\s\S]*?\}\([^)]*\))/);
  if (!match) return null;

  try {
    const context = { window: {} };
    vm.runInNewContext(`window.__NUXT__ = ${match[1]}`, context);
    return context.window.__NUXT__;
  } catch (e) {
    console.error('Failed to parse __NUXT__:', e.message);
    return null;
  }
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
      case 'custom':
        return { lifts: [], runs: [], note: 'Custom extraction required - site-specific implementation needed' };
      default:
        return { error: `Unknown platform: ${resort.platform}` };
    }
  } catch (e) {
    return { error: e.message };
  }
}

/**
 * Run all resorts and generate report
 */
async function runAll() {
  const results = {};

  for (const resort of resorts) {
    console.log(`\n[${resorts.indexOf(resort) + 1}/${resorts.length}] ${resort.name}...`);
    const result = await extractResort(resort.id);
    results[resort.id] = {
      name: resort.name,
      platform: resort.platform,
      openskimap_id: resort.openskimap_id,
      ...result
    };

    if (result.error) {
      console.log(`  ❌ Error: ${result.error}`);
    } else if (result.note) {
      console.log(`  ⚠️  ${result.note}`);
    } else {
      console.log(`  ✓ Lifts: ${result.lifts?.length || 0}, Runs: ${result.runs?.length || 0}`);
    }
  }

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
