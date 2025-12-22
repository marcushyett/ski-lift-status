/**
 * Test script for ski-resort-status module
 */

const { fetchResortStatus, getSupportedResorts } = require('./lib');

async function main() {
  console.log('=== Ski Resort Status Fetcher Test ===\n');

  // List supported resorts
  console.log('Supported resorts:');
  const resorts = getSupportedResorts();
  resorts.forEach(r => {
    console.log(`  - ${r.name} (${r.id}) [${r.platform}]`);
  });

  // Test fetching data for Les Trois Vallées
  console.log('\n=== Fetching Les Trois Vallées ===');
  try {
    const data = await fetchResortStatus('les-trois-vallees');
    console.log(`\nResort: ${data.resort.name}`);
    console.log(`OpenSkiMap ID: ${data.resort.openskimap_id}`);
    console.log(`Lifts: ${data.lifts.length} total`);
    console.log(`  Open: ${data.lifts.filter(l => l.status === 'open').length}`);
    console.log(`  Closed: ${data.lifts.filter(l => l.status === 'closed').length}`);
    console.log(`Runs: ${data.runs.length} total`);
    console.log(`  Open: ${data.runs.filter(r => r.status === 'open').length}`);
    console.log(`  Closed: ${data.runs.filter(r => r.status === 'closed').length}`);

    // Show sample lift
    const sampleLift = data.lifts.find(l => l.status === 'open');
    if (sampleLift) {
      console.log('\nSample Lift:');
      console.log(`  Name: ${sampleLift.name}`);
      console.log(`  Type: ${sampleLift.liftType}`);
      console.log(`  Status: ${sampleLift.status}`);
      console.log(`  OpenSkiMap IDs: ${sampleLift.openskimap_ids.join(', ') || 'none'}`);
      if (sampleLift.capacity) console.log(`  Capacity: ${sampleLift.capacity} persons`);
      if (sampleLift.length) console.log(`  Length: ${sampleLift.length}m`);
    }

    console.log('\n✅ Test passed!');
  } catch (error) {
    console.error('❌ Test failed:', error.message);
    process.exit(1);
  }
}

main();
