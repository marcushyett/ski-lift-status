/**
 * Resort Registry
 * Minimal configuration for supported ski resorts
 */

const RESORTS = [
  {
    id: 'les-trois-vallees',
    name: 'Les Trois Vallées',
    openskimap_id: '68b126bc3175516c9263aed7635d14e37ff360dc',
    platform: 'lumiplan',
    lumiplanMapId: 'bd632c91-6957-494d-95a8-6a72eb87e341'
  },
  {
    id: 'espace-diamant',
    name: 'Espace Diamant',
    openskimap_id: '0345d73f7a4bf0f49815ccb16306a3ec6371544b',
    platform: 'lumiplan',
    lumiplanMapId: '09110215-8a54-42cd-991a-1c534bfb5115'
  },
  {
    id: 'le-grand-domaine',
    name: 'Le Grand Domaine',
    openskimap_id: '97a14cedc5b0e781e9bd9857df1426b9376c7462',
    platform: 'lumiplan',
    lumiplanMapId: 'e4603e2d-1a70-4e9b-ae7c-1b3d760e5a9f'
  },
  {
    id: 'les-sybelles',
    name: 'Les Sybelles',
    openskimap_id: '9bba1f0b01dd1dd8cfd9635a04be9cd1de3f6ab3',
    platform: 'lumiplan',
    lumiplanMapId: 'ec83ba74-a7db-4fb1-9b5e-8c16b7c90a7f'
  }
];

/**
 * Find resort by ID or OpenSkiMap ID
 * @param {string} identifier - Resort ID or OpenSkiMap ID
 * @returns {Object|null} Resort configuration or null if not found
 */
function findResort(identifier) {
  // Try ID match first
  let resort = RESORTS.find(r => r.id === identifier);

  // Try OpenSkiMap ID match
  if (!resort) {
    resort = RESORTS.find(r => r.openskimap_id === identifier);
  }

  return resort || null;
}

/**
 * Get all resorts
 * @returns {Array<Object>} Array of resort configurations
 */
function getAllResorts() {
  return [...RESORTS];
}

/**
 * Get resorts by platform
 * @param {string} platform - Platform name (e.g., 'lumiplan')
 * @returns {Array<Object>} Array of resort configurations for the platform
 */
function getResortsByPlatform(platform) {
  return RESORTS.filter(r => r.platform === platform);
}

module.exports = {
  RESORTS,
  findResort,
  getAllResorts,
  getResortsByPlatform
};
