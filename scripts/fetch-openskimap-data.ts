#!/usr/bin/env tsx
/**
 * Fetch OpenSkiMap Data
 * Downloads resort, lift, and run data from OpenSkiMap
 */

import * as https from 'https';
import * as fs from 'fs';
import * as path from 'path';

const DATA_DIR = path.join(__dirname, '../data');
const BASE_URL = 'https://tiles.openskimap.org/csv';

interface DownloadTask {
  name: string;
  url: string;
  outputPath: string;
}

/**
 * Download file from URL
 */
async function downloadFile(url: string, outputPath: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(outputPath);

    https
      .get(url, (response) => {
        if (response.statusCode === 302 || response.statusCode === 301) {
          // Handle redirect
          const redirectUrl = response.headers.location;
          if (redirectUrl) {
            downloadFile(redirectUrl, outputPath).then(resolve).catch(reject);
            return;
          }
        }

        if (response.statusCode !== 200) {
          reject(new Error(`Failed to download ${url}: ${response.statusCode}`));
          return;
        }

        response.pipe(file);

        file.on('finish', () => {
          file.close();
          resolve();
        });

        file.on('error', (err) => {
          fs.unlink(outputPath, () => {});
          reject(err);
        });
      })
      .on('error', (err) => {
        fs.unlink(outputPath, () => {});
        reject(err);
      });
  });
}

/**
 * Main function
 */
async function main() {
  console.log('Fetching OpenSkiMap data...\n');

  // Ensure data directory exists
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }

  const tasks: DownloadTask[] = [
    {
      name: 'Resorts',
      url: `${BASE_URL}/resorts.csv`,
      outputPath: path.join(DATA_DIR, 'resorts.csv'),
    },
    {
      name: 'Lifts',
      url: `${BASE_URL}/lifts.csv`,
      outputPath: path.join(DATA_DIR, 'lifts.csv'),
    },
    {
      name: 'Runs',
      url: `${BASE_URL}/runs.csv`,
      outputPath: path.join(DATA_DIR, 'runs.csv'),
    },
  ];

  for (const task of tasks) {
    try {
      console.log(`Downloading ${task.name}...`);
      await downloadFile(task.url, task.outputPath);

      // Check file size
      const stats = fs.statSync(task.outputPath);
      const sizeMB = (stats.size / (1024 * 1024)).toFixed(2);
      console.log(`✓ ${task.name}: ${sizeMB} MB\n`);
    } catch (error) {
      console.error(`✗ Failed to download ${task.name}:`);
      console.error(error);
      process.exit(1);
    }
  }

  console.log('✅ All data downloaded successfully!');
}

main().catch((error) => {
  console.error('Error:', error);
  process.exit(1);
});
