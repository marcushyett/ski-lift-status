/**
 * Resort Configs Index
 *
 * Loads all individual resort configuration files from this directory.
 * Each resort has its own .json file for easier maintenance.
 */

const fs = require('fs');
const path = require('path');

// Load all .json files from this directory
const resortsDir = __dirname;
const resorts = [];

// Read all JSON files in the directory
const files = fs.readdirSync(resortsDir)
  .filter(f => f.endsWith('.json'))
  .sort();

for (const file of files) {
  try {
    const filePath = path.join(resortsDir, file);
    const config = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    resorts.push(config);
  } catch (e) {
    console.error(`Error loading ${file}:`, e.message);
  }
}

module.exports = {
  version: "2.0",
  updated: new Date().toISOString().split('T')[0],
  total_resorts: resorts.length,
  resorts
};
