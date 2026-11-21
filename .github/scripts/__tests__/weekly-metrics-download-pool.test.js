const assert = require('node:assert/strict');
const { test } = require('node:test');
const { processInOrder } = require('../weekly_metrics_download_pool');

test('downloads through a three-worker pool and publishes one ordered result at a time', { timeout: 2000 }, async () => {
  const firstReady = Promise.withResolvers();
  const released = Promise.withResolvers();
  const rows = [0, 1, 2, 3, 4, 5];
  const completed = [];
  const published = [];
  let active = 0;
  let peakActive = 0;
  let publishing = false;

  const run = processInOrder(rows, async (row) => {
    active++;
    peakActive = Math.max(peakActive, active);
    if (row === 0) await released.promise;
    else await new Promise(setImmediate);

    completed.push(row);
    if (row === 4) firstReady.resolve();
    active--;
    return { row, status: row === 1 ? 'failed' : 'pass' };
  }, async (result) => {
    assert.equal(publishing, false);
    publishing = true;
    await new Promise(setImmediate);
    published.push(result);
    publishing = false;
  });

  await firstReady.promise;
  assert.ok(completed.includes(1));
  assert.ok(completed.includes(4));
  assert.equal(completed.includes(0), false);
  assert.deepEqual(published, []);
  released.resolve();
  await run;

  assert.equal(peakActive, 3);
  assert.deepEqual(published, rows.map((row) => ({ row, status: row === 1 ? 'failed' : 'pass' })));
});

test('a publisher failure waits for active workers to drain', { timeout: 2000 }, async () => {
  const publishing = Promise.withResolvers();
  const released = Promise.withResolvers();
  const settled = [];
  const run = processInOrder([0, 1, 2], async (row) => {
    if (row !== 0) await released.promise;
    settled.push(row);
    return row;
  }, () => {
    publishing.resolve();
    throw new Error('manifest write failed');
  });
  let rejectionObserved = false;
  const rejected = assert.rejects(run, /manifest write failed/).then(() => { rejectionObserved = true; });
  await publishing.promise;
  await new Promise(setImmediate);
  assert.equal(rejectionObserved, false);
  assert.deepEqual(settled, [0]);
  released.resolve();
  await rejected;
  assert.deepEqual(settled, [0, 1, 2]);
});
