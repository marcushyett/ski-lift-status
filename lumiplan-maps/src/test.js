#!/usr/bin/env node

/**
 * Test script for Lumiplan Ski Data
 * Runs basic tests to verify the module is working correctly
 */

import { getSkiAreaData, getLiftStatus, getRunStatus, getAvailableMaps, LUMIPLAN_MAPS } from './index.js';
import { normalizeName } from './matcher.js';

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`✓ ${name}`);
    passed++;
  } catch (error) {
    console.log(`✗ ${name}`);
    console.log(`  Error: ${error.message}`);
    failed++;
  }
}

async function testAsync(name, fn) {
  try {
    await fn();
    console.log(`✓ ${name}`);
    passed++;
  } catch (error) {
    console.log(`✗ ${name}`);
    console.log(`  Error: ${error.message}`);
    failed++;
  }
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message || 'Assertion failed');
  }
}

async function runTests() {
  console.log('Running Lumiplan Ski Data Tests\n');
  console.log('=================================\n');

  // Test configuration
  console.log('Configuration Tests:');
  test('LUMIPLAN_MAPS should have entries', () => {
    assert(Object.keys(LUMIPLAN_MAPS).length > 0, 'No maps configured');
  });

  test('getAvailableMaps should return array', () => {
    const maps = getAvailableMaps();
    assert(Array.isArray(maps), 'Should return array');
    assert(maps.length > 0, 'Should have maps');
    assert(maps[0].id, 'Maps should have id');
    assert(maps[0].displayName, 'Maps should have displayName');
  });

  // Test name normalization
  console.log('\nName Normalization Tests:');
  test('normalizeName removes prefixes', () => {
    assert(normalizeName('TS des Almes') === 'des almes' || normalizeName('TS des Almes') === 'almes', 'Should remove TS prefix');
    assert(normalizeName('TSD MADELEINE') === 'madeleine', 'Should remove TSD prefix');
  });

  test('normalizeName handles accents', () => {
    assert(normalizeName('Méribel') === 'meribel', 'Should normalize accents');
  });

  // Test API fetching
  console.log('\nAPI Tests (Tignes-ValdIsere):');
  await testAsync('getSkiAreaData should fetch data', async () => {
    const data = await getSkiAreaData('tignes-valdisere', { matchOsm: false });
    assert(data, 'Should return data');
    assert(Array.isArray(data.lifts), 'Should have lifts array');
    assert(Array.isArray(data.runs), 'Should have runs array');
    assert(data.lifts.length > 0, 'Should have some lifts');
    assert(data.runs.length > 0, 'Should have some runs');
    console.log(`    Found ${data.lifts.length} lifts and ${data.runs.length} runs`);
  });

  await testAsync('Lifts should have required fields', async () => {
    const data = await getSkiAreaData('tignes-valdisere', { matchOsm: false });
    const lift = data.lifts[0];
    assert(lift.id, 'Lift should have id');
    assert(lift.name, 'Lift should have name');
    assert(lift.type || lift.liftType, 'Lift should have type');
    assert('status' in lift || 'openingStatus' in lift, 'Lift should have status');
  });

  await testAsync('Runs should have required fields', async () => {
    const data = await getSkiAreaData('tignes-valdisere', { matchOsm: false });
    const run = data.runs[0];
    assert(run.id, 'Run should have id');
    assert(run.name, 'Run should have name');
    assert(run.difficulty || run.trailLevel, 'Run should have difficulty');
  });

  await testAsync('getLiftStatus should return summary', async () => {
    const status = await getLiftStatus('tignes-valdisere');
    assert(typeof status.total === 'number', 'Should have total');
    assert(typeof status.open === 'number', 'Should have open count');
    assert(typeof status.openPercentage === 'number', 'Should have percentage');
    console.log(`    Lifts: ${status.open}/${status.total} open (${status.openPercentage}%)`);
  });

  await testAsync('getRunStatus should return summary', async () => {
    const status = await getRunStatus('tignes-valdisere');
    assert(typeof status.total === 'number', 'Should have total');
    assert(typeof status.open === 'number', 'Should have open count');
    assert(status.byDifficulty, 'Should have byDifficulty');
    console.log(`    Runs: ${status.open}/${status.total} open (${status.openPercentage}%)`);
  });

  // Test other maps
  console.log('\nOther Maps Tests:');
  const otherMaps = ['paradiski', 'les-3-vallees', 'aussois'];
  for (const mapId of otherMaps) {
    await testAsync(`${mapId} should fetch data`, async () => {
      const data = await getSkiAreaData(mapId, { matchOsm: false });
      assert(data.lifts.length > 0, 'Should have lifts');
      assert(data.runs.length > 0, 'Should have runs');
      console.log(`    Found ${data.lifts.length} lifts and ${data.runs.length} runs`);
    });
  }

  // Summary
  console.log('\n=================================');
  console.log(`Tests: ${passed} passed, ${failed} failed`);
  console.log('=================================\n');

  if (failed > 0) {
    process.exit(1);
  }
}

runTests().catch(error => {
  console.error('Test runner failed:', error);
  process.exit(1);
});
