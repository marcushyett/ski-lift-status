/**
 * Name Mapper for OpenSkiMap Integration
 *
 * Maps lift/run names extracted from websites to OpenSkiMap IDs.
 * This is the critical piece that liftie doesn't have.
 */

const fs = require('fs');
const path = require('path');

// Path to CSV data files
const DATA_DIR = path.resolve(__dirname, '../../../data');

/**
 * Parse CSV line handling quoted fields
 */
function parseCSVLine(line) {
  const result = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      result.push(current);
      current = '';
    } else {
      current += char;
    }
  }
  result.push(current);
  return result;
}

/**
 * Parse CSV file into array of objects
 */
function parseCSV(filepath) {
  if (!fs.existsSync(filepath)) {
    console.warn(`CSV file not found: ${filepath}`);
    return [];
  }

  const content = fs.readFileSync(filepath, 'utf-8');
  // Handle Windows line endings
  const lines = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim().split('\n');
  if (lines.length < 2) return [];

  const headers = parseCSVLine(lines[0]).map(h => h.trim());
  const rows = [];

  for (let i = 1; i < lines.length; i++) {
    const values = parseCSVLine(lines[i]);
    const obj = {};
    headers.forEach((header, idx) => {
      obj[header] = (values[idx] || '').trim();
    });
    rows.push(obj);
  }

  return rows;
}

/**
 * Normalize name for matching
 */
function normalizeName(name) {
  if (!name) return '';
  let s = name.trim().toLowerCase();
  // Remove common prefixes
  s = s.replace(/^(le|la|les|l'|the|der|die|das)\s+/i, '');
  // Normalize separators
  s = s.replace(/[-_\s]+/g, ' ');
  // Remove accents (simplified)
  s = s.replace(/[éèêë]/g, 'e')
       .replace(/[àâä]/g, 'a')
       .replace(/[üù]/g, 'u')
       .replace(/[öô]/g, 'o')
       .replace(/[ç]/g, 'c')
       .replace(/[ñ]/g, 'n');
  return s.trim();
}

/**
 * Calculate simple fuzzy match score (0-100)
 */
function fuzzyScore(str1, str2) {
  const s1 = normalizeName(str1);
  const s2 = normalizeName(str2);

  if (s1 === s2) return 100;
  if (!s1 || !s2) return 0;

  // Check if one contains the other
  if (s1.includes(s2) || s2.includes(s1)) {
    const longer = Math.max(s1.length, s2.length);
    const shorter = Math.min(s1.length, s2.length);
    return Math.round((shorter / longer) * 100);
  }

  // Levenshtein distance
  const matrix = [];
  for (let i = 0; i <= s1.length; i++) {
    matrix[i] = [i];
  }
  for (let j = 0; j <= s2.length; j++) {
    matrix[0][j] = j;
  }
  for (let i = 1; i <= s1.length; i++) {
    for (let j = 1; j <= s2.length; j++) {
      const cost = s1[i - 1] === s2[j - 1] ? 0 : 1;
      matrix[i][j] = Math.min(
        matrix[i - 1][j] + 1,
        matrix[i][j - 1] + 1,
        matrix[i - 1][j - 1] + cost
      );
    }
  }

  const distance = matrix[s1.length][s2.length];
  const maxLen = Math.max(s1.length, s2.length);
  return Math.round((1 - distance / maxLen) * 100);
}

/**
 * Load reference data for a resort from CSV files
 */
function loadReferenceData(resortId) {
  const liftsPath = path.join(DATA_DIR, 'lifts.csv');
  const runsPath = path.join(DATA_DIR, 'runs.csv');

  const allLifts = parseCSV(liftsPath);
  const allRuns = parseCSV(runsPath);

  // Filter by resort ID
  const lifts = allLifts.filter(lift =>
    lift.ski_area_ids && lift.ski_area_ids.includes(resortId)
  );

  const runs = allRuns.filter(run =>
    run.ski_area_ids && run.ski_area_ids.includes(resortId) && run.name
  );

  return { lifts, runs };
}

/**
 * Map online names to OpenSkiMap reference data
 */
function mapNames(onlineNames, referenceEntities, options = {}) {
  const {
    nameField = 'name',
    idField = 'id',
    fuzzyThreshold = 75
  } = options;

  const results = {
    mapped: [],
    unmapped: [],
    coverage: 0
  };

  // Build lookup tables
  const exactLookup = new Map();
  const normalizedLookup = new Map();

  referenceEntities.forEach(entity => {
    const name = entity[nameField];
    if (!name) return;
    exactLookup.set(name, entity);
    exactLookup.set(name.toLowerCase(), entity);
    normalizedLookup.set(normalizeName(name), entity);
  });

  const mappedIds = new Set();

  for (const onlineName of onlineNames) {
    if (!onlineName) continue;

    // Try exact match
    let entity = exactLookup.get(onlineName) || exactLookup.get(onlineName.toLowerCase());
    if (entity) {
      results.mapped.push({
        online_name: onlineName,
        openskimap_id: entity[idField],
        openskimap_name: entity[nameField],
        match_type: 'exact',
        confidence: 1.0
      });
      mappedIds.add(entity[idField]);
      continue;
    }

    // Try normalized match
    entity = normalizedLookup.get(normalizeName(onlineName));
    if (entity) {
      results.mapped.push({
        online_name: onlineName,
        openskimap_id: entity[idField],
        openskimap_name: entity[nameField],
        match_type: 'normalized',
        confidence: 0.9
      });
      mappedIds.add(entity[idField]);
      continue;
    }

    // Try fuzzy match
    let bestMatch = null;
    let bestScore = 0;

    for (const refEntity of referenceEntities) {
      const refName = refEntity[nameField];
      if (!refName) continue;

      const score = fuzzyScore(onlineName, refName);
      if (score > bestScore && score >= fuzzyThreshold) {
        bestScore = score;
        bestMatch = refEntity;
      }
    }

    if (bestMatch) {
      results.mapped.push({
        online_name: onlineName,
        openskimap_id: bestMatch[idField],
        openskimap_name: bestMatch[nameField],
        match_type: 'fuzzy',
        confidence: bestScore / 100
      });
      mappedIds.add(bestMatch[idField]);
    } else {
      results.unmapped.push(onlineName);
    }
  }

  // Calculate coverage
  if (referenceEntities.length > 0) {
    results.coverage = (mappedIds.size / referenceEntities.length) * 100;
  }

  results.referenceCount = referenceEntities.length;
  results.mappedCount = results.mapped.length;
  results.unmappedCount = results.unmapped.length;

  return results;
}

/**
 * Map extracted resort data to OpenSkiMap
 */
function mapResortToOpenSkiMap(resortId, extractedData) {
  const { lifts: refLifts, runs: refRuns } = loadReferenceData(resortId);

  const extractedLiftNames = (extractedData.lifts || []).map(l => l.name).filter(Boolean);
  const extractedRunNames = (extractedData.runs || []).map(r => r.name).filter(Boolean);

  const liftMappings = mapNames(extractedLiftNames, refLifts);
  const runMappings = mapNames(extractedRunNames, refRuns);

  // Merge status from extracted data into mappings
  const liftStatusMap = new Map();
  (extractedData.lifts || []).forEach(l => {
    if (l.name) liftStatusMap.set(l.name, l.status);
  });

  const runStatusMap = new Map();
  (extractedData.runs || []).forEach(r => {
    if (r.name) runStatusMap.set(r.name, r.status);
  });

  // Add status to mappings
  liftMappings.mapped.forEach(m => {
    m.status = liftStatusMap.get(m.online_name) || 'unknown';
  });

  runMappings.mapped.forEach(m => {
    m.status = runStatusMap.get(m.online_name) || 'unknown';
  });

  return {
    resortId,
    lifts: liftMappings,
    runs: runMappings,
    summary: {
      lifts: {
        extracted: extractedLiftNames.length,
        reference: refLifts.length,
        mapped: liftMappings.mappedCount,
        coverage: liftMappings.coverage.toFixed(1) + '%'
      },
      runs: {
        extracted: extractedRunNames.length,
        reference: refRuns.length,
        mapped: runMappings.mappedCount,
        coverage: runMappings.coverage.toFixed(1) + '%'
      }
    }
  };
}

module.exports = {
  loadReferenceData,
  mapNames,
  mapResortToOpenSkiMap,
  normalizeName,
  fuzzyScore
};
