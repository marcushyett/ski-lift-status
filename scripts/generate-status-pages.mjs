#!/usr/bin/env node
/**
 * Generate status_pages.csv by:
 * 1. Aggregating lifts.csv to find top 50 resorts by lift count
 * 2. Searching Serper.dev for each resort's status page
 * 3. Using OpenAI to pick the official status page URL
 */

import fs from 'fs';
import path from 'path';

const SERPER_API_KEY = process.env.SERPER;
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const TOP_N = 50;

// Parse CSV line handling quoted fields
function parseCSVLine(line) {
  const parts = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (c === '"') inQuotes = !inQuotes;
    else if (c === ',' && !inQuotes) {
      parts.push(current);
      current = '';
    } else {
      current += c;
    }
  }
  parts.push(current);
  return parts;
}

// Aggregate lifts by ski_area_id
function aggregateLifts(liftsPath) {
  const data = fs.readFileSync(liftsPath, 'utf-8');
  const lines = data.split('\n').slice(1).filter(l => l.trim());

  const counts = {};
  const resortNames = {};

  lines.forEach(line => {
    const parts = parseCSVLine(line);
    const skiAreaNames = parts[7] || '';
    const skiAreaIds = parts[8] || '';

    if (skiAreaIds) {
      skiAreaIds.split(';').forEach((id, idx) => {
        id = id.trim();
        if (id) {
          counts[id] = (counts[id] || 0) + 1;
          if (!resortNames[id] && skiAreaNames) {
            const names = skiAreaNames.split(',');
            resortNames[id] = (names[idx] || names[0] || '').trim();
          }
        }
      });
    }
  });

  // Sort by count descending and take top N
  const sorted = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, TOP_N)
    .map(([id, count]) => ({
      resort_id: id,
      resort_name: resortNames[id] || 'Unknown',
      lift_count: count
    }));

  return sorted;
}

// Search Serper.dev
async function searchSerper(query) {
  const response = await fetch('https://google.serper.dev/search', {
    method: 'POST',
    headers: {
      'X-API-KEY': SERPER_API_KEY,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      q: query,
      num: 10
    })
  });

  if (!response.ok) {
    throw new Error(`Serper API error: ${response.status}`);
  }

  return response.json();
}

// Use OpenAI to pick the best status page URL
async function pickBestUrl(resortName, searchResults) {
  const organic = searchResults.organic || [];
  if (organic.length === 0) {
    return null;
  }

  const resultsText = organic.map((r, i) =>
    `${i + 1}. Title: ${r.title}\n   URL: ${r.link}\n   Snippet: ${r.snippet || ''}`
  ).join('\n\n');

  const prompt = `You are helping find the official lift status page for the ski resort "${resortName}".

Below are search results for "${resortName} lift status". Pick the single best URL that:
1. Is the official resort website (not a third-party aggregator like skiresort.info, snow-forecast.com, onthesnow.com, etc.)
2. Shows live lift status or operating conditions
3. Is the most direct link to the status/conditions page (not the homepage)

Search results:
${resultsText}

Respond with ONLY the URL of the best result, or "NONE" if no official status page is found.
Do not include any explanation, just the URL or "NONE".`;

  const response = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${OPENAI_API_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model: 'gpt-4o-mini',
      messages: [{ role: 'user', content: prompt }],
      temperature: 0,
      max_tokens: 200
    })
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`OpenAI API error: ${response.status} - ${errText}`);
  }

  const data = await response.json();
  const answer = data.choices[0]?.message?.content?.trim();

  if (!answer || answer === 'NONE' || answer.toLowerCase() === 'none') {
    return null;
  }

  return answer;
}

// Escape CSV field
function escapeCSV(field) {
  if (field == null) return '';
  const str = String(field);
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

// Main function
async function main() {
  console.log('Aggregating lifts data...');
  const liftsPath = path.join(process.cwd(), 'data', 'lifts.csv');
  const topResorts = aggregateLifts(liftsPath);

  console.log(`Found top ${topResorts.length} resorts by lift count:\n`);
  topResorts.forEach((r, i) => {
    console.log(`${i + 1}. ${r.resort_name}: ${r.lift_count} lifts`);
  });

  console.log('\nSearching for status pages...\n');

  const results = [];

  for (let i = 0; i < topResorts.length; i++) {
    const resort = topResorts[i];
    console.log(`[${i + 1}/${topResorts.length}] Searching: ${resort.resort_name}...`);

    try {
      // Search for lift status
      const query = `${resort.resort_name} ski lift status`;
      const searchResults = await searchSerper(query);

      // Use LLM to pick best URL
      const statusUrl = await pickBestUrl(resort.resort_name, searchResults);

      results.push({
        ...resort,
        status_page_url: statusUrl || ''
      });

      if (statusUrl) {
        console.log(`   Found: ${statusUrl}`);
      } else {
        console.log(`   No official status page found`);
      }

      // Rate limiting - be gentle with APIs
      await new Promise(r => setTimeout(r, 500));

    } catch (err) {
      console.error(`   Error: ${err.message}`);
      results.push({
        ...resort,
        status_page_url: ''
      });
    }
  }

  // Write CSV
  const outputPath = path.join(process.cwd(), 'data', 'status_pages.csv');
  const header = 'resort_id,resort_name,lift_count,status_page_url';
  const rows = results.map(r =>
    [r.resort_id, r.resort_name, r.lift_count, r.status_page_url]
      .map(escapeCSV)
      .join(',')
  );

  fs.writeFileSync(outputPath, [header, ...rows].join('\n') + '\n');

  console.log(`\nWrote ${results.length} resorts to ${outputPath}`);
  console.log(`Resorts with status pages: ${results.filter(r => r.status_page_url).length}`);
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
