#!/usr/bin/env tsx
/**
 * Discover Status Pages
 * Finds lift/run status pages for ski resorts using AI
 */

import * as https from 'https';
import * as fs from 'fs';
import * as path from 'path';

const DATA_DIR = path.join(__dirname, '../data');
const SERPER_API_KEY = process.env.SERPER_API_KEY;
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;

interface Resort {
  id: string;
  name: string;
  countries: string;
  websites: string;
}

interface SearchResult {
  title: string;
  link: string;
  snippet: string;
}

interface DiscoveryResult {
  resort_id: string;
  resort_name: string;
  success: boolean;
  status_page_url: string | null;
  confidence: number;
}

/**
 * Make HTTPS request
 */
async function httpsRequest(options: https.RequestOptions, data?: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => (body += chunk));
      res.on('end', () => {
        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
          resolve(body);
        } else {
          reject(new Error(`HTTP ${res.statusCode}: ${body}`));
        }
      });
    });

    req.on('error', reject);
    if (data) req.write(data);
    req.end();
  });
}

/**
 * Search for resort status pages using Serper
 */
async function searchStatusPage(resortName: string, website: string): Promise<SearchResult[]> {
  if (!SERPER_API_KEY) {
    throw new Error('SERPER_API_KEY environment variable is required');
  }

  const query = `${resortName} lift status piste map live`;
  const searchData = JSON.stringify({ q: query, num: 5 });

  const options: https.RequestOptions = {
    hostname: 'google.serper.dev',
    path: '/search',
    method: 'POST',
    headers: {
      'X-API-KEY': SERPER_API_KEY,
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(searchData),
    },
  };

  const response = await httpsRequest(options, searchData);
  const data = JSON.parse(response);

  return (data.organic || []).map((result: any) => ({
    title: result.title,
    link: result.link,
    snippet: result.snippet,
  }));
}

/**
 * Analyze search results using OpenAI
 */
async function analyzeResults(
  resortName: string,
  results: SearchResult[]
): Promise<{ url: string | null; confidence: number }> {
  if (!OPENAI_API_KEY) {
    throw new Error('OPENAI_API_KEY environment variable is required');
  }

  const prompt = `You are analyzing search results to find the official lift/run status page for "${resortName}" ski resort.

Search results:
${results.map((r, i) => `${i + 1}. ${r.title}\n   URL: ${r.link}\n   ${r.snippet}`).join('\n\n')}

Which URL is most likely the official live lift/run status page? Respond with ONLY a JSON object:
{
  "url": "the best URL or null if none found",
  "confidence": 0.0-1.0,
  "reason": "brief explanation"
}`;

  const requestData = JSON.stringify({
    model: 'gpt-4o-mini',
    messages: [
      {
        role: 'system',
        content: 'You are a helpful assistant that identifies official ski resort status pages.',
      },
      { role: 'user', content: prompt },
    ],
    temperature: 0.3,
    response_format: { type: 'json_object' },
  });

  const options: https.RequestOptions = {
    hostname: 'api.openai.com',
    path: '/v1/chat/completions',
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${OPENAI_API_KEY}`,
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(requestData),
    },
  };

  const response = await httpsRequest(options, requestData);
  const data = JSON.parse(response);

  const content = data.choices[0].message.content;
  const analysis = JSON.parse(content);

  return {
    url: analysis.url,
    confidence: analysis.confidence,
  };
}

/**
 * Load resorts from CSV
 */
function loadResorts(limit?: number): Resort[] {
  const csvPath = path.join(DATA_DIR, 'resorts.csv');
  const content = fs.readFileSync(csvPath, 'utf-8');
  const lines = content.split('\n').filter((l) => l.trim());

  const resorts: Resort[] = [];
  for (let i = 1; i < lines.length; i++) {
    // Skip header
    const parts = lines[i]!.split(',');
    if (parts.length >= 4) {
      resorts.push({
        id: parts[0]!,
        name: parts[1]!,
        countries: parts[2]!,
        websites: parts[5] || '',
      });
    }

    if (limit && resorts.length >= limit) break;
  }

  return resorts;
}

/**
 * Save results to CSV
 */
function saveResults(results: DiscoveryResult[], outputPath: string) {
  const csv = [
    'resort_id,resort_name,status_page_url,confidence',
    ...results.map(
      (r) =>
        `${r.resort_id},"${r.resort_name}",${r.status_page_url || ''},${r.confidence.toFixed(2)}`
    ),
  ].join('\n');

  fs.writeFileSync(outputPath, csv, 'utf-8');
}

/**
 * Main discovery function
 */
async function discover(options: { top?: number; all?: boolean; resortId?: string; override?: boolean }) {
  console.log('🔍 Starting status page discovery...\n');

  let resorts: Resort[];

  if (options.resortId) {
    const allResorts = loadResorts();
    const resort = allResorts.find((r) => r.id === options.resortId);
    if (!resort) {
      throw new Error(`Resort not found: ${options.resortId}`);
    }
    resorts = [resort];
  } else if (options.all) {
    resorts = loadResorts();
  } else {
    resorts = loadResorts(options.top || 30);
  }

  console.log(`Processing ${resorts.length} resorts...\n`);

  const results: DiscoveryResult[] = [];

  for (let i = 0; i < resorts.length; i++) {
    const resort = resorts[i]!;
    console.log(`[${i + 1}/${resorts.length}] ${resort.name}`);

    try {
      // Search for status page
      const searchResults = await searchStatusPage(resort.name, resort.websites);

      if (searchResults.length === 0) {
        console.log('  ❌ No search results found\n');
        results.push({
          resort_id: resort.id,
          resort_name: resort.name,
          success: false,
          status_page_url: null,
          confidence: 0,
        });
        continue;
      }

      // Analyze with AI
      const analysis = await analyzeResults(resort.name, searchResults);

      if (analysis.url) {
        console.log(`  ✅ Found: ${analysis.url} (${(analysis.confidence * 100).toFixed(0)}%)\n`);
        results.push({
          resort_id: resort.id,
          resort_name: resort.name,
          success: true,
          status_page_url: analysis.url,
          confidence: analysis.confidence,
        });
      } else {
        console.log('  ❌ No suitable page found\n');
        results.push({
          resort_id: resort.id,
          resort_name: resort.name,
          success: false,
          status_page_url: null,
          confidence: 0,
        });
      }

      // Rate limiting
      await new Promise((resolve) => setTimeout(resolve, 1000));
    } catch (error) {
      console.log(`  ❌ Error: ${error}\n`);
      results.push({
        resort_id: resort.id,
        resort_name: resort.name,
        success: false,
        status_page_url: null,
        confidence: 0,
      });
    }
  }

  // Save results
  const outputPath = path.join(DATA_DIR, 'status_pages.csv');
  saveResults(results, outputPath);

  const jsonPath = 'discovery-results.json';
  const summary = {
    total: results.length,
    successful: results.filter((r) => r.success).length,
    failed: results.filter((r) => !r.success).length,
    results,
  };
  fs.writeFileSync(jsonPath, JSON.stringify(summary, null, 2));

  console.log('\n📊 Summary:');
  console.log(`  Total: ${summary.total}`);
  console.log(`  Successful: ${summary.successful}`);
  console.log(`  Failed: ${summary.failed}`);
  console.log(`\n✅ Results saved to ${outputPath}`);
  console.log(`📄 JSON output: ${jsonPath}`);
}

/**
 * CLI
 */
async function main() {
  const args = process.argv.slice(2);

  const options = {
    top: args.includes('--top') ? parseInt(args[args.indexOf('--top') + 1] || '30') : undefined,
    all: args.includes('--all'),
    resortId: args.includes('--resort-id') ? args[args.indexOf('--resort-id') + 1] : undefined,
    override: args.includes('--override'),
  };

  // Validate API keys
  if (!SERPER_API_KEY) {
    console.error('❌ SERPER_API_KEY environment variable is required');
    process.exit(1);
  }

  if (!OPENAI_API_KEY) {
    console.error('❌ OPENAI_API_KEY environment variable is required');
    process.exit(1);
  }

  await discover(options);
}

if (require.main === module) {
  main().catch((error) => {
    console.error('Error:', error);
    process.exit(1);
  });
}

export { discover };
