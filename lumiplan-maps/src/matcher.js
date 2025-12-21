/**
 * Fuzzy Matcher for OpenSkiMap IDs
 * Matches Lumiplan lift/run names to OpenSkiMap data using fuzzy matching
 */

import Fuse from 'fuse.js';

/**
 * Normalize a name for better matching
 * @param {string} name - Original name
 * @returns {string} Normalized name
 */
export function normalizeName(name) {
  if (!name) return '';

  return name
    .toLowerCase()
    // Remove common prefixes
    .replace(/^(ts|tsd|tc|tcd|tk|tm|tf|tp|cab|fun|tel)\s+/i, '')
    .replace(/^(télésiège|téléski|télécabine|téléphérique|funiculaire)\s+/i, '')
    .replace(/^(chairlift|gondola|cable car|funicular|drag lift|t-bar|platter)\s+/i, '')
    // Normalize accents
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    // Remove special characters
    .replace(/['-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Create a Fuse.js instance for matching
 * @param {Array<Object>} items - Items to search (must have 'name' and 'id' fields)
 * @returns {Fuse} Fuse.js instance
 */
export function createMatcher(items) {
  // Pre-process items with normalized names
  const processedItems = items.map(item => ({
    ...item,
    normalizedName: normalizeName(item.name)
  }));

  return new Fuse(processedItems, {
    keys: ['name', 'normalizedName'],
    threshold: 0.4,
    distance: 100,
    includeScore: true,
    ignoreLocation: true
  });
}

/**
 * Find the best match for a Lumiplan item
 * @param {Fuse} matcher - Fuse.js instance
 * @param {string} name - Name to match
 * @returns {Object|null} Best match with score, or null if no good match
 */
export function findBestMatch(matcher, name) {
  if (!name) return null;

  const normalizedQuery = normalizeName(name);
  const results = matcher.search(normalizedQuery);

  if (results.length === 0) {
    return null;
  }

  const best = results[0];

  // Only accept matches with a reasonable score
  if (best.score > 0.5) {
    return null;
  }

  return {
    osmId: best.item.id,
    osmName: best.item.name,
    score: best.score,
    confidence: best.score < 0.1 ? 'high' : best.score < 0.3 ? 'medium' : 'low'
  };
}

/**
 * Match all Lumiplan items to OpenSkiMap data
 * @param {Array<Object>} lumiplanItems - Lumiplan lifts or runs
 * @param {Array<Object>} osmItems - OpenSkiMap items
 * @returns {Array<Object>} Items with osmMatch field added
 */
export function matchAllItems(lumiplanItems, osmItems) {
  if (!osmItems || osmItems.length === 0) {
    return lumiplanItems;
  }

  const matcher = createMatcher(osmItems);

  return lumiplanItems.map(item => {
    const match = findBestMatch(matcher, item.name);
    return {
      ...item,
      osmMatch: match
    };
  });
}

/**
 * Load OpenSkiMap data from CSV
 * This is a simple parser for the ski-lift-status CSV format
 * @param {string} csvContent - CSV file content
 * @param {Array<string>} skiAreaIds - OpenSkiMap ski area IDs to filter by
 * @returns {Array<Object>} Parsed items
 */
export function parseOpenSkiMapCSV(csvContent, skiAreaIds = []) {
  const lines = csvContent.split('\n');
  if (lines.length < 2) return [];

  const headers = lines[0].split(',');
  const items = [];

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    // Simple CSV parsing (doesn't handle escaped quotes properly for complex cases)
    const values = parseCSVLine(line);
    if (values.length !== headers.length) continue;

    const item = {};
    headers.forEach((header, idx) => {
      item[header.trim()] = values[idx];
    });

    // Filter by ski area IDs if provided
    if (skiAreaIds.length > 0) {
      const itemAreaIds = (item.ski_area_ids || '').split(';');
      const hasMatch = itemAreaIds.some(id => skiAreaIds.includes(id));
      if (!hasMatch) continue;
    }

    items.push({
      id: item.id,
      name: item.name,
      type: item.lift_type || item.run_type || item.difficulty
    });
  }

  return items;
}

/**
 * Parse a CSV line handling quoted values
 * @param {string} line - CSV line
 * @returns {Array<string>} Parsed values
 */
function parseCSVLine(line) {
  const values = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];

    if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      values.push(current);
      current = '';
    } else {
      current += char;
    }
  }
  values.push(current);

  return values;
}
