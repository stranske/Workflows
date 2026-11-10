'use strict';

// Include the executable source/template workflow regressions in the script
// acceptance gate. These exercise verification, explicit continuation, reporting,
// and ownership cleanup together rather than only the pure transition helper.
require('../../../tests/workflows/auto_pilot_verify_handoff.test.js');
