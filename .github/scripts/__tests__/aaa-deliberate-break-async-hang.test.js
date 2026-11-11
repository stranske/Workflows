// DELIBERATE BREAK (reverted before merge): an async test that never settles.
const test = require('node:test');
test('deliberate break: awaits forever', async () => { await new Promise(() => {}); });
