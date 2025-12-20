/**
 * Vail Resorts platform extractor
 * Used by all Vail/Epic Pass resorts
 *
 * Inspired by liftie: https://github.com/pirxpilot/liftie/blob/main/lib/tools/vail.js
 */

const statuses = ['closed', 'open', 'hold', 'scheduled'];

module.exports = {
  // Extract from embedded JavaScript data
  extractFromScript: true,

  // Pattern to find the data script
  scriptPattern: 'TerrainStatusFeed = {',

  // How to extract the data
  extract: (scriptContent) => {
    // Find and parse the TerrainStatusFeed object
    const match = scriptContent.match(/FR\.TerrainStatusFeed\s*=\s*(\{[\s\S]*?\});/);
    if (!match) return [];

    try {
      // Safely evaluate the object (in real implementation, use a proper parser)
      const data = JSON.parse(match[1].replace(/'/g, '"'));
      return (data.Lifts || []).map(lift => ({
        name: lift.Name.trim(),
        status: statuses[lift.Status] || 'closed'
      }));
    } catch {
      return [];
    }
  }
};
