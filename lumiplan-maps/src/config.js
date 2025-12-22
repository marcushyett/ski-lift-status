/**
 * Lumiplan Interactive Map Configuration
 * Maps Lumiplan map names to their UUIDs and OpenSkiMap resort IDs
 */

export const LUMIPLAN_MAPS = {
  'tignes-valdisere': {
    mapName: 'Tignes_ValdIsere',
    uuid: '84a526a4-c935-455e-a9c5-037061d75ba4',
    displayName: 'Tignes - Val d\'Isère (Espace Killy)',
    // OpenSkiMap ski area IDs for resorts within this domain
    openSkiMapIds: ['6ed5f25f0eb3e366ee2e0e667d998c0bf551225f'],
    // Lumiplan internal resort IDs mapped to names
    lumiplanResorts: {
      '653': 'Tignes',
      '664': 'Val d\'Isère'
    }
  },

  'paradiski': {
    mapName: 'Paradiski',
    uuid: 'e6302a83-ce5b-4717-bab8-4f282b1083d7',
    displayName: 'Paradiski (Les Arcs, La Plagne, Peisey-Vallandry)',
    openSkiMapIds: [
      'dec537b602584db89d89ab114a619f1ae356398e', // Les Arcs
      'f47f7e05cc676b25b6a00f77f0b86a897f03018c'  // La Plagne
    ],
    lumiplanResorts: {
      '520': 'Les Arcs',
      '497': 'La Plagne',
      '515': 'Peisey-Vallandry'
    }
  },

  'les-3-vallees': {
    mapName: 'les-3-vallees',
    uuid: 'bd632c91-6957-494d-95a8-6a72eb87e341',
    displayName: 'Les 3 Vallées',
    openSkiMapIds: [
      '3ab7375c4734163405f0f77a7c5a6afdfd600b73', // Val Thorens - Orelle
      '68b126bc3175516c9263aed7635d14e37ff360dc'  // Les Trois Vallées
    ],
    lumiplanResorts: {
      '815': 'Méribel-Mottaret',
      '833': 'Courchevel',
      '848': 'Val Thorens',
      '859': 'Orelle',
      '863': 'Méribel-Alpina',
      '874': 'Les Menuires'
    }
  },

  'aussois': {
    mapName: 'Aussois',
    uuid: 'e68b5cdd-02c4-43f9-b75f-2c679445b626',
    displayName: 'Aussois',
    openSkiMapIds: ['a0ffbaaaf9807c58da7fecab4df2617502f1d584'],
    lumiplanResorts: {
      '274': 'Aussois'
    }
  },

  'orcieres': {
    mapName: 'Orcieres',
    uuid: '6789b50e-22ec-4f68-b3ad-73f047c3cfdd',
    displayName: 'Orcières Merlette 1850',
    openSkiMapIds: ['824c7b22068010ed9590671f95a41f7eaf5f3819'],
    lumiplanResorts: {
      '335': 'Orcières 1850'
    }
  },

  'vaujany': {
    mapName: 'Vaujany',
    uuid: 'c3a3e312-e191-436b-aefb-abf54eaa0b04',
    displayName: 'Alpe d\'Huez Grand Domaine (Vaujany, Oz)',
    openSkiMapIds: ['721dd142d0af653027c7569e1bd0799586bdefa1'],
    lumiplanResorts: {
      '601': 'Oz-Vaujany',
      '610': 'Alpe d\'Huez'
    }
  }
};

// Base URL for Lumiplan API
export const LUMIPLAN_API_BASE = 'https://lumiplay.link/interactive-map-services/public/map';

// Lift type mappings from Lumiplan to standardized types
export const LIFT_TYPE_MAP = {
  'SURFACE_LIFT': 'drag_lift',
  'CHAIRLIFT': 'chair_lift',
  'DETACHABLE_CHAIRLIFT': 'chair_lift',
  'GONDOLA': 'gondola',
  'CABLE_CAR': 'cable_car',
  'FUNICULAR': 'funicular',
  'MAGIC_CARPET': 'magic_carpet',
  'PLATTER': 'platter',
  'T_BAR': 't-bar',
  'ROPE_TOW': 'rope_tow'
};

// Trail difficulty mappings from Lumiplan to standardized
export const TRAIL_DIFFICULTY_MAP = {
  'GREEN': 'novice',
  'BLUE': 'easy',
  'RED': 'intermediate',
  'BLACK': 'advanced',
  'DOUBLE_BLACK': 'expert'
};

// Opening status mappings
export const OPENING_STATUS_MAP = {
  'OPEN': 'open',
  'CLOSED': 'closed',
  'FORECAST': 'scheduled',
  'UNKNOWN': 'unknown'
};
