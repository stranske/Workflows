// DELIBERATE BREAK (reverted before merge): a test blocked in a synchronous
// child, which also leaves an orphan (sleep 900) re-parented away from it.
const test = require('node:test');
const { execFileSync } = require('child_process');
test('deliberate break: blocked in execFileSync', () => {
  execFileSync('sh', ['-c', '(sleep 900 >/dev/null 2>&1 &); sleep 600']);
});
