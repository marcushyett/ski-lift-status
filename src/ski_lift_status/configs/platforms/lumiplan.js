/**
 * Lumiplan platform extractor
 * Used by many French resorts via bulletin.lumiplan.pro
 *
 * Inspired by liftie: https://github.com/pirxpilot/liftie/blob/main/lib/tools/lumiplan.js
 */

module.exports = {
  // Data URL pattern - replace {station}, {region}, {pays} with resort values
  dataUrlTemplate: 'https://bulletin.lumiplan.pro/bulletin.php?station={station}&region={region}&pays={pays}&lang=en',

  // Selector for lift groups
  selector: '.text:contains(Lifts) + .prl_affichage .prl_group',

  parse: {
    name: {
      child: '1/0',  // Navigate to child 1, then child 0
      text: true,
      transform: (name) => name.replace(/\s+/g, ' ').trim()
    },
    status: {
      child: '4/0',
      attribute: 'src',
      regex: /(.)\.svg$/,
      transform: (match) => {
        switch (match) {
          case 'O':
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
