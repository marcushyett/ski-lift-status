/**
 * OpenSkiMap Matcher for Lumiplan Data
 * Matches Lumiplan lift/run names to OpenSkiMap IDs using fuzzy matching
 */

const fs = require('fs');
const path = require('path');

// Path to OpenSkiMap CSV data
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
    return [];
  }

  const content = fs.readFileSync(filepath, 'utf-8');
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
  s = s.replace(/^(le|la|les|l'|the|der|die|das)\s+/i, '');
  s = s.replace(/[-_\s]+/g, ' ');
  s = s.replace(/[éèêë]/g, 'e')
       .replace(/[àâä]/g, 'a')
       .replace(/[üù]/g, 'u')
       .replace(/[öô]/g, 'o')
       .replace(/[ç]/g, 'c')
       .replace(/[ñ]/g, 'n');
  return s.trim();
}

/**
 * Calculate fuzzy match score using Levenshtein distance
 */
function fuzzyScore(str1, str2) {
  const s1 = normalizeName(str1);
  const s2 = normalizeName(str2);

  if (s1 === s2) return 100;
  if (!s1 || !s2) return 0;

  if (s1.includes(s2) || s2.includes(s1)) {
    const longer = Math.max(s1.length, s2.length);
    const shorter = Math.min(s1.length, s2.length);
    return Math.round((shorter / longer) * 100);
  }

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
 * Load OpenSkiMap reference data for a resort
 */
function loadReferenceData(openskimapId) {
  const liftsPath = path.join(DATA_DIR, 'lifts.csv');
  const runsPath = path.join(DATA_DIR, 'runs.csv');

  const allLifts = parseCSV(liftsPath);
  const allRuns = parseCSV(runsPath);

  const lifts = allLifts.filter(lift =>
    lift.ski_area_ids && lift.ski_area_ids.includes(openskimapId)
  );

  const runs = allRuns.filter(run =>
    run.ski_area_ids && run.ski_area_ids.includes(openskimapId) && run.name
  );

  return { lifts, runs };
}

/**
 * Normalize lift type for matching
 */
function normalizeLiftType(lumiplanType) {
  if (!lumiplanType) return null;
  const type = lumiplanType.toUpperCase();
  if (type.includes('GONDOLA') || type.includes('CABIN')) return 'gondola';
  if (type.includes('CHAIRLIFT') || type.includes('CHAIR')) return 'chair_lift';
  if (type.includes('PLATTER') || type.includes('SURFACE')) return 'platter';
  if (type.includes('T-BAR') || type.includes('TBAR')) return 't-bar';
  if (type.includes('MAGIC_CARPET')) return 'magic_carpet';
  if (type.includes('ROPE_TOW')) return 'rope_tow';
  if (type.includes('CABLE_CAR')) return 'cable_car';
  if (type.includes('FUNITEL')) return 'mixed_lift';
  if (type.includes('TRAM')) return 'cable_car';
  return null;
}

/**
 * Normalize difficulty for matching
 */
function normalizeDifficulty(lumiplanLevel) {
  if (!lumiplanLevel) return null;
  const level = lumiplanLevel.toUpperCase();
  if (level.includes('GREEN')) return 'novice';
  if (level.includes('BLUE')) return 'easy';
  if (level.includes('RED')) return 'intermediate';
  if (level.includes('BLACK')) return 'advanced';
  return null;
}

/**
 * Find matching OpenSkiMap IDs for a lift/run
 * @param {string} name - Lift/run name from Lumiplan
 * @param {Array} referenceData - OpenSkiMap reference entities
 * @param {Object} hint - Disambiguation hint (type or difficulty)
 * @returns {Array<string>} Array of matching OpenSkiMap IDs
 */
function findMatches(name, referenceData, hint = {}) {
  if (!name) return [];

  // Build lookup maps
  const byName = new Map();
  const byNormalized = new Map();

  referenceData.forEach(entity => {
    if (!entity.name) return;
    const lower = entity.name.toLowerCase();
    const normalized = normalizeName(entity.name);

    if (!byName.has(lower)) byName.set(lower, []);
    byName.get(lower).push(entity);

    if (!byNormalized.has(normalized)) byNormalized.set(normalized, []);
    byNormalized.get(normalized).push(entity);
  });

  let candidates = [];

  // Try exact match
  candidates = byName.get(name.toLowerCase()) || [];

  // Try normalized match
  if (candidates.length === 0) {
    candidates = byNormalized.get(normalizeName(name)) || [];
  }

  // Try fuzzy match
  if (candidates.length === 0) {
    for (const entity of referenceData) {
      if (!entity.name) continue;
      const score = fuzzyScore(name, entity.name);
      if (score >= 75) {
        candidates.push(entity);
      }
    }
  }

  if (candidates.length === 0) return [];
  if (candidates.length === 1) return [candidates[0].id];

  // Disambiguate using hint
  if (hint.type || hint.difficulty) {
    const filtered = candidates.filter(c => {
      if (hint.type && c.lift_type) {
        return c.lift_type === hint.type;
      }
      if (hint.difficulty && c.difficulty) {
        return c.difficulty === hint.difficulty;
      }
      return true;
    });

    if (filtered.length > 0) {
      return filtered.map(c => c.id);
    }
  }

  // Return all candidates
  return candidates.map(c => c.id);
}

module.exports = {
  loadReferenceData,
  normalizeLiftType,
  normalizeDifficulty,
  findMatches,
  normalizeName,
  fuzzyScore
};
