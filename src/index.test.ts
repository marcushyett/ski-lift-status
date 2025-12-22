/**
 * Tests for ski-resort-status module
 */

import { describe, it, expect } from 'vitest';
import { fetchResortStatus, getSupportedResorts, getResort } from './index';

describe('ski-resort-status', () => {
  describe('getSupportedResorts', () => {
    it('should return a list of supported resorts', () => {
      const resorts = getSupportedResorts();

      expect(resorts).toBeInstanceOf(Array);
      expect(resorts.length).toBeGreaterThan(0);

      // Check structure of first resort
      const resort = resorts[0];
      expect(resort).toHaveProperty('id');
      expect(resort).toHaveProperty('name');
      expect(resort).toHaveProperty('openskimap_id');
      expect(resort).toHaveProperty('platform');

      // Check OpenSkiMap ID format (40 char hex)
      expect(resort!.openskimap_id).toMatch(/^[a-f0-9]{40}$/);
    });
  });

  describe('getResort', () => {
    it('should find resort by ID', () => {
      const resort = getResort('les-trois-vallees');

      expect(resort).toBeDefined();
      expect(resort?.name).toBe('Les Trois Vallées');
      expect(resort?.platform).toBe('lumiplan');
    });

    it('should find resort by OpenSkiMap ID', () => {
      const resort = getResort('68b126bc3175516c9263aed7635d14e37ff360dc');

      expect(resort).toBeDefined();
      expect(resort?.name).toBe('Les Trois Vallées');
    });

    it('should return null for unknown resort', () => {
      const resort = getResort('non-existent-resort');

      expect(resort).toBeNull();
    });
  });

  describe('fetchResortStatus', () => {
    it('should fetch live status for Les Trois Vallées', async () => {
      const data = await fetchResortStatus('les-trois-vallees');

      // Check resort info
      expect(data.resort).toBeDefined();
      expect(data.resort.name).toBe('Les Trois Vallées');
      expect(data.resort.openskimap_id).toBe('68b126bc3175516c9263aed7635d14e37ff360dc');

      // Check lifts
      expect(data.lifts).toBeInstanceOf(Array);
      expect(data.lifts.length).toBeGreaterThan(0);

      // Check lift structure
      const lift = data.lifts[0];
      expect(lift).toHaveProperty('name');
      expect(lift).toHaveProperty('status');
      expect(lift).toHaveProperty('liftType');
      expect(lift).toHaveProperty('openskimap_ids');
      expect(['open', 'closed', 'scheduled']).toContain(lift!.status);

      // Check runs
      expect(data.runs).toBeInstanceOf(Array);
      expect(data.runs.length).toBeGreaterThan(0);

      // Check run structure
      const run = data.runs[0];
      expect(run).toHaveProperty('name');
      expect(run).toHaveProperty('status');
      expect(run).toHaveProperty('openskimap_ids');
      expect(['open', 'closed', 'scheduled']).toContain(run!.status);
    }, 30000); // 30 second timeout for API call

    it('should throw error for unknown resort', async () => {
      await expect(fetchResortStatus('non-existent-resort')).rejects.toThrow('Resort not found');
    });

    it('should validate returned data with Zod schema', async () => {
      // This test ensures Zod validation is working
      const data = await fetchResortStatus('les-trois-vallees');

      // If we get here without error, Zod validation passed
      expect(data).toBeDefined();
      expect(data.resort).toBeDefined();
      expect(data.lifts).toBeDefined();
      expect(data.runs).toBeDefined();
    }, 30000);
  });
});
