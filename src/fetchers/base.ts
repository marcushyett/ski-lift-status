/**
 * Base Fetcher Interface
 * All platform-specific fetchers should extend this class
 */

import { validateResortStatus } from '../schema';
import type { ResortStatus, ResortConfig, FetcherMetadata } from '../schema';

export abstract class BaseFetcher {
  protected config: ResortConfig;

  constructor(config: ResortConfig) {
    this.config = config;
  }

  /**
   * Fetch live status data for a resort
   * This method must be implemented by subclasses
   * The returned data will be automatically validated against the schema
   */
  protected abstract fetchData(): Promise<ResortStatus>;

  /**
   * Public fetch method with automatic schema validation
   * This ensures all fetchers return consistent, validated data
   */
  async fetch(): Promise<ResortStatus> {
    const data = await this.fetchData();

    // Validate the data against our Zod schema
    // This will throw a ZodError with detailed messages if validation fails
    return validateResortStatus(data);
  }

  /**
   * Get fetcher metadata
   * Should be implemented by subclasses to provide platform info
   */
  static getMetadata(): FetcherMetadata {
    return {
      platform: 'base',
      version: '1.0.0',
      description: 'Base fetcher interface',
    };
  }
}
