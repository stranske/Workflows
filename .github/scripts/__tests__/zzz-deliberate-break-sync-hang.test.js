// DELIBERATE BREAK (reverted before merge): a test blocked in a synchronous child.
const test = require('node:test');
const { execFileSync } = require('child_process');
test('deliberate break: blocked in execFileSync', () => { execFileSync('sleep', ['600']); });
