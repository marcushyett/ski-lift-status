/**
 * Base Fetcher Interface
 * All platform-specific fetchers should extend this class
 */
class BaseFetcher {
  constructor(config) {
    this.config = config;
  }

  /**
   * Fetch live status data for a resort
   * @returns {Promise<{resort, lifts, runs}>}
   */
  async fetch() {
    throw new Error('fetch() must be implemented by subclass');
  }

  /**
   * Get fetcher metadata
   * @returns {{platform: string, version: string}}
   */
  static getMetadata() {
    return {
      platform: 'base',
      version: '1.0.0'
    };
  }
}

module.exports = BaseFetcher;
