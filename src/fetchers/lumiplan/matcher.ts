/**
 * OpenSkiMap Matcher for Lumiplan Data
 * Matches Lumiplan lift/run names to OpenSkiMap IDs using fuzzy matching
 */

import * as fs from 'fs';
import * as path from 'path';

// Path to OpenSkiMap CSV data
const DATA_DIR = path.resolve(__dirname, '../../../data');

/**
 * OpenSkiMap lift/run entity
 */
export interface OpenSkiMapEntity {
  id: string;
  name: string;
  ski_area_ids?: string;
  lift_type?: string;
  difficulty?: string;
}

/**
 * Reference data for a resort
 */
export interface ReferenceData {
  lifts: OpenSkiMapEntity[];
  runs: OpenSkiMapEntity[];
}

/**
 * Matching hint for disambiguation
 */
export interface MatchingHint {
  type?: string | null;
  difficulty?: string | null;
}

/**
 * Parse CSV line handling quoted fields
 */
function parseCSVLine(line: string): string[] {
  const result: string[] = [];
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
function parseCSV(filepath: string): OpenSkiMapEntity[] {
  if (!fs.existsSync(filepath)) {
    return [];
  }

  const content = fs.readFileSync(filepath, 'utf-8');
  const lines = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim().split('\n');
  if (lines.length < 2) return [];

  const headers = parseCSVLine(lines[0]!).map((h) => h.trim());
  const rows: OpenSkiMapEntity[] = [];

  for (let i = 1; i < lines.length; i++) {
    const values = parseCSVLine(lines[i]!);
    const obj: any = {};
    headers.forEach((header, idx) => {
      obj[header] = (values[idx] || '').trim();
    });
    // Ensure required fields exist
    if (obj.id && obj.name) {
      rows.push(obj as OpenSkiMapEntity);
    }
  }

  return rows;
}

/**
 * Normalize name for matching
 */
export function normalizeName(name: string | undefined | null): string {
  if (!name) return '';
  let s = name.trim().toLowerCase();
  s = s.replace(/^(le|la|les|l'|the|der|die|das)\s+/i, '');
  s = s.replace(/[-_\s]+/g, ' ');
  s = s
    .replace(/[éèêë]/g, 'e')
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
export function fuzzyScore(str1: string, str2: string): number {
  const s1 = normalizeName(str1);
  const s2 = normalizeName(str2);

  if (s1 === s2) return 100;
  if (!s1 || !s2) return 0;

  if (s1.includes(s2) || s2.includes(s1)) {
    const longer = Math.max(s1.length, s2.length);
    const shorter = Math.min(s1.length, s2.length);
    return Math.round((shorter / longer) * 100);
  }

  const matrix: number[][] = [];
  for (let i = 0; i <= s1.length; i++) {
    matrix[i] = [i];
  }
  for (let j = 0; j <= s2.length; j++) {
    matrix[0]![j] = j;
  }
  for (let i = 1; i <= s1.length; i++) {
    for (let j = 1; j <= s2.length; j++) {
      const cost = s1[i - 1] === s2[j - 1] ? 0 : 1;
      matrix[i]![j] = Math.min(
        matrix[i - 1]![j]! + 1,
        matrix[i]![j - 1]! + 1,
        matrix[i - 1]![j - 1]! + cost
      );
    }
  }

  const distance = matrix[s1.length]![s2.length]!;
  const maxLen = Math.max(s1.length, s2.length);
  return Math.round((1 - distance / maxLen) * 100);
}

/**
 * Load OpenSkiMap reference data for a resort
 * Accepts either a single OpenSkiMap ID or an array of IDs (for multi-resort areas like Paradiski)
 */
export function loadReferenceData(openskimapId: string | string[]): ReferenceData {
  const liftsPath = path.join(DATA_DIR, 'lifts.csv');
  const runsPath = path.join(DATA_DIR, 'runs.csv');

  const allLifts = parseCSV(liftsPath);
  const allRuns = parseCSV(runsPath);

  const ids = Array.isArray(openskimapId) ? openskimapId : [openskimapId];

  const lifts = allLifts.filter((lift) =>
    lift.ski_area_ids && ids.some(id => lift.ski_area_ids!.includes(id))
  );

  const runs = allRuns.filter((run) =>
    run.ski_area_ids && run.name && ids.some(id => run.ski_area_ids!.includes(id))
  );

  return { lifts, runs };
}

/**
 * Normalize lift type for matching
 */
export function normalizeLiftType(lumiplanType: string | undefined | null): string | null {
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
export function normalizeDifficulty(lumiplanLevel: string | undefined | null): string | null {
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
 */
export function findMatches(name: string, referenceData: OpenSkiMapEntity[], hint: MatchingHint = {}): string[] {
  if (!name) return [];

  // Build lookup maps
  const byName = new Map<string, OpenSkiMapEntity[]>();
  const byNormalized = new Map<string, OpenSkiMapEntity[]>();

  referenceData.forEach((entity) => {
    const entityName = entity.name;
    if (!entityName) return;
    const lower = entityName.toLowerCase();
    const normalized = normalizeName(entityName);

    if (!byName.has(lower)) byName.set(lower, []);
    byName.get(lower)!.push(entity);

    if (!byNormalized.has(normalized)) byNormalized.set(normalized, []);
    byNormalized.get(normalized)!.push(entity);
  });

  let candidates: OpenSkiMapEntity[] = [];

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
  if (candidates.length === 1) return [candidates[0]!.id];

  // Disambiguate using hint
  if (hint.type || hint.difficulty) {
    const filtered = candidates.filter((c) => {
      if (hint.type && c.lift_type) {
        return c.lift_type === hint.type;
      }
      if (hint.difficulty && c.difficulty) {
        return c.difficulty === hint.difficulty;
      }
      return true;
    });

    if (filtered.length > 0) {
      return filtered.map((c) => c.id);
    }
  }

  // Return all candidates
  return candidates.map((c) => c.id);
}
