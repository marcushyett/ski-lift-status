#!/usr/bin/env node
/**
 * CLI tool for ski-resort-status
 * Usage: npx ski-resort-status <resort-id-or-openskimap-id>
 */

import { fetchResortStatus, getSupportedResorts } from './index';

async function main() {
  const args = process.argv.slice(2);

  // Show help
  if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
    console.log(`
Ski Resort Status CLI

Usage:
  npx ski-resort-status <resort-id-or-openskimap-id>
  npx ski-resort-status --list

Options:
  --list, -l        List all supported resorts
  --help, -h        Show this help message
  --json            Output raw JSON

Examples:
  npx ski-resort-status les-trois-vallees
  npx ski-resort-status 68b126bc3175516c9263aed7635d14e37ff360dc
  npx ski-resort-status --list
`);
    process.exit(0);
  }

  // List resorts
  if (args.includes('--list') || args.includes('-l')) {
    console.log('\n📍 Supported Resorts:\n');
    const resorts = getSupportedResorts();
    resorts.forEach((r) => {
      console.log(`  ${r.name}`);
      console.log(`    ID: ${r.id}`);
      console.log(`    OpenSkiMap ID: ${r.openskimap_id}`);
      console.log(`    Platform: ${r.platform}\n`);
    });
    console.log(`Total: ${resorts.length} resorts\n`);
    process.exit(0);
  }

  const resortIdentifier = args[0];
  const jsonOutput = args.includes('--json');

  if (!resortIdentifier) {
    console.error('❌ Error: Please provide a resort ID or OpenSkiMap ID');
    console.error('   Run with --help for usage information');
    process.exit(1);
  }

  try {
    console.log(`\n🎿 Fetching status for: ${resortIdentifier}...\n`);

    const data = await fetchResortStatus(resortIdentifier);

    if (jsonOutput) {
      console.log(JSON.stringify(data, null, 2));
      process.exit(0);
    }

    // Pretty output
    console.log(`📍 ${data.resort.name}`);
    console.log(`   OpenSkiMap ID: ${data.resort.openskimap_id}`);
    console.log('');

    // Lifts summary
    const openLifts = data.lifts.filter((l) => l.status === 'open').length;
    const closedLifts = data.lifts.filter((l) => l.status === 'closed').length;
    const scheduledLifts = data.lifts.filter((l) => l.status === 'scheduled').length;

    console.log(`🚡 Lifts (${data.lifts.length} total)`);
    console.log(`   ✅ Open: ${openLifts}`);
    console.log(`   ❌ Closed: ${closedLifts}`);
    if (scheduledLifts > 0) console.log(`   📅 Scheduled: ${scheduledLifts}`);
    console.log('');

    // Runs summary
    const openRuns = data.runs.filter((r) => r.status === 'open').length;
    const closedRuns = data.runs.filter((r) => r.status === 'closed').length;
    const scheduledRuns = data.runs.filter((r) => r.status === 'scheduled').length;

    console.log(`⛷️  Runs (${data.runs.length} total)`);
    console.log(`   ✅ Open: ${openRuns}`);
    console.log(`   ❌ Closed: ${closedRuns}`);
    if (scheduledRuns > 0) console.log(`   📅 Scheduled: ${scheduledRuns}`);
    console.log('');

    // Sample lift
    const sampleLift = data.lifts.find((l) => l.status === 'open');
    if (sampleLift) {
      console.log(`📋 Sample Lift: ${sampleLift.name}`);
      console.log(`   Status: ${sampleLift.status}`);
      console.log(`   Type: ${sampleLift.liftType}`);
      if (sampleLift.capacity) console.log(`   Capacity: ${sampleLift.capacity} p/h`);
      if (sampleLift.length) console.log(`   Length: ${sampleLift.length}m`);
      console.log('');
    }

    // Sample run
    const sampleRun = data.runs.find((r) => r.status === 'open');
    if (sampleRun) {
      console.log(`📋 Sample Run: ${sampleRun.name}`);
      console.log(`   Status: ${sampleRun.status}`);
      if (sampleRun.level) console.log(`   Level: ${sampleRun.level}`);
      if (sampleRun.length) console.log(`   Length: ${sampleRun.length}m`);
      if (sampleRun.groomingStatus) console.log(`   Grooming: ${sampleRun.groomingStatus}`);
      console.log('');
    }

    console.log('✅ Done! Use --json flag for full data\n');
  } catch (error) {
    if (error instanceof Error) {
      console.error(`\n❌ Error: ${error.message}\n`);
    } else {
      console.error('\n❌ An unknown error occurred\n');
    }
    process.exit(1);
  }
}

main();
