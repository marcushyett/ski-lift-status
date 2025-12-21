#!/usr/bin/env node

/**
 * Test script to verify Playwright is installed and working.
 *
 * Usage: node scripts/test_playwright.mjs [url]
 *
 * If no URL is provided, tests basic browser functionality.
 * If a URL is provided, navigates to that page and captures XHR/Fetch requests.
 */

import { chromium } from 'playwright';

async function testPlaywright(url) {
    console.log('Starting Playwright test...\n');

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();

    // Collect XHR/Fetch requests
    const apiRequests = [];

    page.on('request', request => {
        const resourceType = request.resourceType();
        if (resourceType === 'xhr' || resourceType === 'fetch') {
            apiRequests.push({
                url: request.url(),
                method: request.method(),
                resourceType
            });
        }
    });

    try {
        console.log(`Navigating to: ${url}\n`);

        await page.goto(url, {
            waitUntil: 'networkidle',
            timeout: 60000
        });

        console.log('Page loaded successfully!');
        console.log(`Page title: ${await page.title()}\n`);

        if (apiRequests.length > 0) {
            console.log('=== API/XHR Requests Captured ===\n');
            apiRequests.forEach((req, i) => {
                console.log(`${i + 1}. [${req.method}] ${req.url}`);
            });
        } else {
            console.log('No XHR/Fetch requests captured on this page.');
        }

        console.log('\n=== Playwright is working correctly! ===');

    } catch (error) {
        console.error('Error:', error.message);
        console.log('\nNote: The browser launched successfully.');
        console.log('Network errors may occur for external sites in restricted environments.');
    } finally {
        await browser.close();
    }
}

// Get URL from command line args or use default
const url = process.argv[2] || 'http://example.com';
testPlaywright(url);
