/**
 * Lumiplan Fetcher
 * Fetches live ski resort data from Lumiplan interactive maps
 */

import { BaseFetcher } from '../base';
import * as api from './api';
import * as matcher from './matcher';
import type { ResortStatus, Status } from '../../schema';
import type { LumiplanResortConfig } from '../../resorts';
import type { LumiplanDynamicItem } from './api';

export class LumiplanFetcher extends BaseFetcher {
  protected config: LumiplanResortConfig;

  constructor(config: LumiplanResortConfig) {
    super(config);
    this.config = config;

    if (!config.lumiplanMapId) {
      throw new Error('lumiplanMapId is required for Lumiplan fetcher');
    }
  }

  /**
   * Fetch live status data from Lumiplan API
   * This method is called by BaseFetcher.fetch() which handles validation
   */
  protected async fetchData(): Promise<ResortStatus> {
    const { lumiplanMapId, openskimap_id } = this.config;

    // Fetch data from Lumiplan API
    const { static: staticData, dynamic: dynamicData } = await api.fetchMapData(lumiplanMapId);

    // Build dynamic status map
    const statusMap = new Map<string, LumiplanDynamicItem>();
    for (const item of dynamicData.items || []) {
      statusMap.set(item.id, item);
    }

    // Load OpenSkiMap reference data for matching
    let refLifts: matcher.OpenSkiMapEntity[] = [];
    let refRuns: matcher.OpenSkiMapEntity[] = [];
    if (openskimap_id) {
      const refData = matcher.loadReferenceData(openskimap_id);
      refLifts = refData.lifts;
      refRuns = refData.runs;
    }

    const lifts: ResortStatus['lifts'] = [];
    const runs: ResortStatus['runs'] = [];

    // Process static items
    for (const item of staticData.items || []) {
      const data = item.data || {};
      const { name, type, id } = data;

      if (!name || !type || !id) continue;

      const dynamicItem = statusMap.get(id);
      const status = this.normalizeStatus(dynamicItem?.openingStatus);

      if (type === 'LIFT') {
        const normalizedType = matcher.normalizeLiftType(data.liftType);
        const osmIds = matcher.findMatches(name, refLifts, { type: normalizedType });

        lifts.push({
          name,
          status,
          liftType: data.liftType || 'unknown',
          openskimap_ids: osmIds,
          // Static metadata
          capacity: data.capacity,
          duration: data.duration,
          length: data.length,
          uphillCapacity: data.uphillCapacity,
          speed: data.speed,
          arrivalAltitude: data.arrivalAltitude,
          departureAltitude: data.departureAltitude,
          openingTimesTheoretic: data.openingTimesTheoretic,
          // Dynamic real-time data
          openingTimesReal: dynamicItem?.openingTimesReal,
          operating: dynamicItem?.operating,
          openingStatus: dynamicItem?.openingStatus,
          waitingTime: dynamicItem?.waiting,
          message: dynamicItem?.message?.content,
        });
      } else if (type === 'TRAIL') {
        const normalizedDifficulty = matcher.normalizeDifficulty(data.trailLevel);
        const osmIds = matcher.findMatches(name, refRuns, { difficulty: normalizedDifficulty });

        runs.push({
          name,
          status,
          trailType: data.trailType,
          level: data.trailLevel,
          openskimap_ids: osmIds,
          // Static metadata
          length: data.length,
          surface: data.surface,
          arrivalAltitude: data.arrivalAltitude,
          departureAltitude: data.departureAltitude,
          averageSlope: data.averageSlope,
          exposure: data.exposure,
          guaranteedSnow: data.guaranteedSnow,
          openingTimesTheoretic: data.openingTimesTheoretic,
          // Dynamic real-time data
          openingTimesReal: dynamicItem?.openingTimesReal,
          operating: dynamicItem?.operating,
          openingStatus: dynamicItem?.openingStatus,
          groomingStatus: dynamicItem?.groomingStatus,
          snowQuality: dynamicItem?.snowQuality,
          message: dynamicItem?.message?.content,
        });
      }
    }

    return {
      resort: {
        id: this.config.id,
        name: this.config.name,
        openskimap_id: this.config.openskimap_id,
      },
      lifts,
      runs,
    };
  }

  /**
   * Normalize Lumiplan opening status to standard format
   */
  private normalizeStatus(apiStatus: string | undefined): Status {
    switch (apiStatus) {
      case 'OPEN':
        return 'open';
      case 'FORECAST':
      case 'DELAYED':
        return 'scheduled';
      default:
        return 'closed';
    }
  }

  /**
   * Get fetcher metadata
   */
  static override getMetadata() {
    return {
      platform: 'lumiplan',
      version: '2.0.0',
      description: 'Lumiplan interactive maps fetcher',
    };
  }
}
