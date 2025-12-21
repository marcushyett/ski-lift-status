#!/usr/bin/env bash

# Install Chromium and Playwright for browser automation
# This script is run by the Claude SessionStart hook

set -e

echo "Installing Playwright and Chromium..."

# Change to project directory
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || cd "$(dirname "$0")/.."

# Install playwright package locally if not already installed
if [ ! -d "node_modules/playwright" ]; then
    echo "Installing Playwright locally..."
    npm install playwright
fi

# Install Chromium browser for Playwright
echo "Installing Chromium browser..."
npx playwright install chromium 2>/dev/null || true

echo "Playwright and Chromium installation complete!"
