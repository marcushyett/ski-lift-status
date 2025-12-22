/**
 * Resort Registry
 * Minimal configuration for supported ski resorts
 */

import { ResortConfigSchema } from './schema';
import type { ResortConfig } from './schema';

/**
 * Lumiplan-specific resort configuration
 */
export interface LumiplanResortConfig extends ResortConfig {
  platform: 'lumiplan';
  lumiplanMapId: string;
}

const RESORTS: LumiplanResortConfig[] = [
  {
    id: 'les-trois-vallees',
    name: 'Les Trois Vallées',
    openskimap_id: '68b126bc3175516c9263aed7635d14e37ff360dc',
    platform: 'lumiplan',
    lumiplanMapId: 'bd632c91-6957-494d-95a8-6a72eb87e341',
  },
  {
    id: 'espace-diamant',
    name: 'Espace Diamant',
    openskimap_id: '0345d73f7a4bf0f49815ccb16306a3ec6371544b',
    platform: 'lumiplan',
    lumiplanMapId: '09110215-8a54-42cd-991a-1c534bfb5115',
  },
  {
    id: 'le-grand-domaine',
    name: 'Le Grand Domaine',
    openskimap_id: '97a14cedc5b0e781e9bd9857df1426b9376c7462',
    platform: 'lumiplan',
    lumiplanMapId: 'e4603e2d-1a70-4e9b-ae7c-1b3d760e5a9f',
  },
  {
    id: 'les-sybelles',
    name: 'Les Sybelles',
    openskimap_id: '9bba1f0b01dd1dd8cfd9635a04be9cd1de3f6ab3',
    platform: 'lumiplan',
    lumiplanMapId: 'ec83ba74-a7db-4fb1-9b5e-8c16b7c90a7f',
  },
  {
    id: 'paradiski',
    name: 'Paradiski',
    openskimap_id: [
      'f47f7e05cc676b25b6a00f77f0b86a897f03018c', // La Plagne
      'dec537b602584db89d89ab114a619f1ae356398e', // Les Arcs
    ],
    platform: 'lumiplan',
    lumiplanMapId: 'e6302a83-ce5b-4717-bab8-4f282b1083d7',
  },
];

// Validate all resort configurations at module load time
RESORTS.forEach((resort) => {
  ResortConfigSchema.parse(resort);
});

/**
 * Find resort by ID or OpenSkiMap ID
 */
export function findResort(identifier: string): LumiplanResortConfig | null {
  // Try ID match first
  let resort = RESORTS.find((r) => r.id === identifier);

  // Try OpenSkiMap ID match
  if (!resort) {
    resort = RESORTS.find((r) => r.openskimap_id === identifier);
  }

  return resort || null;
}

/**
 * Get all resorts
 */
export function getAllResorts(): LumiplanResortConfig[] {
  return [...RESORTS];
}

/**
 * Get resorts by platform
 */
export function getResortsByPlatform(platform: string): LumiplanResortConfig[] {
  return RESORTS.filter((r) => r.platform === platform);
}

export { RESORTS };
