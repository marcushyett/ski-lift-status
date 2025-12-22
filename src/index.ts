/**
 * Ski Resort Status Fetcher
 * Main entry point for fetching live ski resort data
 */

import * as resorts from './resorts';
import { LumiplanFetcher } from './fetchers/lumiplan';
import type { ResortStatus, ResortConfig } from './schema';
import { BaseFetcher } from './fetchers/base';

// Type for fetcher constructor
type FetcherConstructor = new (config: any) => BaseFetcher;

// Map of platform names to fetcher classes
const FETCHERS: Record<string, FetcherConstructor> = {
  lumiplan: LumiplanFetcher,
};

/**
 * Fetch live status data for a resort
 */
export async function fetchResortStatus(resortIdOrOsmId: string): Promise<ResortStatus> {
  const config = resorts.findResort(resortIdOrOsmId);

  if (!config) {
    throw new Error(`Resort not found: ${resortIdOrOsmId}`);
  }

  const FetcherClass = FETCHERS[config.platform];

  if (!FetcherClass) {
    throw new Error(`Unsupported platform: ${config.platform}`);
  }

  const fetcher = new FetcherClass(config);
  return await fetcher.fetch();
}

/**
 * Resort summary for getSupportedResorts()
 */
export interface ResortSummary {
  id: string;
  name: string;
  openskimap_id: string;
  platform: string;
}

/**
 * Get list of all supported resorts
 */
export function getSupportedResorts(): ResortSummary[] {
  return resorts.getAllResorts().map((r) => ({
    id: r.id,
    name: r.name,
    openskimap_id: r.openskimap_id,
    platform: r.platform,
  }));
}

/**
 * Get resort configuration
 */
export function getResort(resortIdOrOsmId: string): ResortConfig | null {
  return resorts.findResort(resortIdOrOsmId);
}

/**
 * Export fetcher classes for advanced usage
 */
export const fetchers = {
  LumiplanFetcher,
};

/**
 * Export schema types and validators
 */
export * from './schema';
