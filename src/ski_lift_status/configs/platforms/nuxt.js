/**
 * Nuxt.js platform extractor
 * Extracts data from __NUXT__ embedded state
 * Used by sites like cervinia.it (Zermatt/Breuil-Cervinia)
 */

module.exports = {
  // Extract from __NUXT__ script
  extractNuxt: true,

  // Default paths for common Nuxt.js ski resort patterns
  defaultPaths: {
    lifts: '$.state.impianti.SECTEUR[*].REMONTEE[*]',
    runs: '$.state.impianti.SECTEUR[*].PISTE[*]'
  },

  // How to extract name and status from each item
  parse: {
    name: '@attributes.nom',
    status: {
      path: '@attributes.etat',
      transform: (status) => {
        switch (status) {
          case 'O':
          case 'A':
            return 'open';
          case 'P':
            return 'scheduled';
          default:
            return 'closed';
        }
      }
    }
  }
};
