/**
 * Skiplan platform extractor
 * Used by many French ski resorts
 *
 * Inspired by liftie: https://github.com/pirxpilot/liftie/blob/main/lib/tools/skiplan.js
 */

module.exports = {
  // Selector for lift rows
  selector: '.rm',

  // How to extract name and status from each row
  parse: {
    // Name is in the 3rd child element (index 2)
    name: { child: 2, text: true },
    // Status is in the class of the 1st child (index 0)
    status: {
      child: 0,
      attribute: 'class',
      transform: (classes) => {
        const status = classes.split(' ').pop();
        switch (status) {
          case 'ouvert':
          case 'open':
            return 'open';
          case 'prevision':
          case 'scheduled':
            return 'scheduled';
          default:
            return 'closed';
        }
      }
    }
  }
};
