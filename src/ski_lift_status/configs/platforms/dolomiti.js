/**
 * Dolomiti Superski platform extractor
 * Used by Italian Dolomiti resorts
 *
 * Inspired by liftie: https://github.com/pirxpilot/liftie/blob/main/lib/tools/dolomitisuperski.js
 */

module.exports = {
  // Selector for lift table rows
  selector: '.table tbody tr',

  parse: {
    name: {
      child: 1,  // Second column has the name
      text: true
    },
    status: {
      child: 3,  // Fourth column has status indicator
      attribute: 'class',
      regex: /\b(red|green)\b/,
      transform: (match) => {
        switch (match) {
          case 'green':
            return 'open';
          default:
            return 'closed';
        }
      }
    }
  }
};
