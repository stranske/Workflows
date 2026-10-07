'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { fork } = require('node:child_process');
const { presenceServer } = require('./helpers/keepalive-presence-server.js');

function reporterProcess(server, surface, number) {
  return new Promise((resolve, reject) => {
    const child = fork(require.resolve('./helpers/presence-process.js'),
      [require.resolve(`${surface}/keepalive_reporter_applicability.js`), String(number)],
      { stdio: ['ignore', 'ignore', 'pipe', 'ipc'] });
    let result;
    let stderr = '';
    child.stderr.on('data', (data) => { stderr += data; });
    child.on('error', reject);
    child.on('message', async (message) => {
      if (message.done) { result = message; return; }
      try {
        const value = await server.request(message.method, message.path, message.body);
        child.send({ id: message.id, value });
      } catch (error) {
        child.send({ id: message.id, error: { message: error.message, status: error.status } });
      }
    });
    child.on('exit', (code) => {
      if (code !== 0 || !result) reject(new Error(`Child ${code}: ${stderr}`));
      else resolve(result);
    });
  });
}

for (const surface of ['..', '../../../templates/consumer-repo/.github/scripts']) {
  const { hasAttemptIndexesForPr } = require(`${surface}/keepalive_authority_state.js`);
  const read = (server, number) => hasAttemptIndexesForPr(server.request, 'owner/repo', number);

  test(`${surface}: separate processes read only new blobs across repeated legacy churn`, async () => {
    const server = presenceServer();
    assert.deepEqual((await reporterProcess(server, surface, 42)).value, { prNumber: 42, results: [] });
    assert.equal(server.stats().blobs, 1001);
    for (let i = 0; i < 3; i += 1) {
      server.addAttempt(44 + i, 10000 + i);
      const before = server.stats().blobs;
      assert.match((await reporterProcess(server, surface, 44 + i)).error, /ledger is missing/);
      assert.equal(server.stats().blobs - before, 1, 'exactly one delta blob per added index');
      assert.deepEqual((await reporterProcess(server, surface, 42)).value, { prNumber: 42, results: [] });
      assert.equal(server.stats().blobs - before, 1, 'unchanged entries never re-read');
    }
    server.addAttempt(50, 11000); server.addAttempt(51, 11001);
    const before = server.stats().blobs;
    assert.equal(await read(server, 51), true);
    assert.equal(server.stats().blobs - before, 2);
  });

  test(`${surface}: replacements revalidate blobs and removals recompute membership`, async () => {
    const server = presenceServer({ count: 2 });
    assert.equal(await read(server, 9000), true);
    server.replaceAttempt(1, 44);
    assert.equal(await read(server, 44), true);
    assert.equal(server.stats().blobs, 3);
    server.removeAttempt(2);
    assert.equal(await read(server, 9000), false);
    assert.equal(await read(server, 44), true);
    assert.equal(server.stats().blobs, 3, 'removal reads no historical blobs');
  });

  test(`${surface}: corrupt mappings reject even when positive membership agrees`, async () => {
    for (const edit of [
      (value) => { value.entries.pop(); },
      (value) => { value.entries[0].blob_sha = 'f'.repeat(40); },
      (value) => { value.entries.push(value.entries[0]); },
      (value) => { value.entries[0].pr_number = 44; },
    ]) {
      const server = presenceServer({ count: 2 });
      await read(server, 42);
      server.corruptInventory(edit);
      await assert.rejects(read(server, 42), /manifest/);
      server.addAttempt(44);
      await assert.rejects(read(server, 44), /manifest/);
    }
  });

  test(`${surface}: changes during delta and checkpoint writes reject positive and negative reads`, async () => {
    for (const number of [42, 9000]) {
      for (const phase of ['delta', 'manifest', 'checkpoint']) {
        const server = presenceServer({ count: 2 });
        await read(server, 42); server.addAttempt(44);
        let changed = false;
        server.setHook(({ method, path }) => {
          const match = phase === 'delta' ? path.includes('/git/blobs/') :
            method === 'PUT' && (phase === 'checkpoint' ? path.endsWith('/checkpoint.json') :
              !path.endsWith('/checkpoint.json'));
          if (!changed && match) { changed = true; server.addAttempt(45, 12000); }
        });
        await assert.rejects(read(server, number), /changed during/);
        server.setHook(() => {});
        assert.equal(await read(server, 45), true);
      }
    }
  });

  test(`${surface}: checkpoint CAS loser cannot overwrite a newer complete snapshot`, async () => {
    const server = presenceServer({ count: 2 });
    await read(server, 42); server.addAttempt(44);
    let raced = false;
    const request = async (method, path, body) => {
      if (!raced && method === 'PUT' && path.endsWith('/checkpoint.json')) {
        raced = true;
        server.addAttempt(45, 12000);
        await read(server, 45);
      }
      return server.request(method, path, body);
    };
    await assert.rejects(hasAttemptIndexesForPr(request, 'owner/repo', 42), /checkpoint conflict/);
    const before = server.stats().blobs;
    assert.equal(await read(server, 44), true);
    assert.equal(await read(server, 45), true);
    assert.equal(server.stats().blobs, before, 'newer checkpoint survives the stale writer');
  });

  test(`${surface}: missing expected checkpoint cannot silently restart full-history migration`, async () => {
    const server = presenceServer({ count: 2 });
    await read(server, 42); server.dropCheckpoint(); server.addAttempt(44);
    const before = server.stats().blobs;
    await assert.rejects(read(server, 44), /checkpoint missing/);
    assert.equal(server.stats().blobs, before);
  });

  test(`${surface}: conflicting complete mappings reject even with the same positive set`, async () => {
    const server = presenceServer({ count: 2 }); server.addAttempt(44);
    let corrupted = false;
    server.setHook(({ method, path }) => {
      if (!corrupted && method === 'PUT' && !path.endsWith('/checkpoint.json')) {
        corrupted = true;
        server.corruptInventory((value) => {
          const first = value.entries.find((entry) => entry.pr_number === 44);
          const second = value.entries.find((entry) => entry.pr_number === 9000);
          [first.pr_number, second.pr_number] = [second.pr_number, first.pr_number];
        });
      }
    });
    await assert.rejects(read(server, 42), /conflicts with validated inventory/);
  });

  test(`${surface}: partial delta and lost writes deny the current read and recover independently`, async () => {
    for (const phase of ['delta', 'manifest', 'checkpoint']) {
      const server = presenceServer({ count: 2 }); await read(server, 42);
      server.addAttempt(44);
      let failed = false;
      server.setHook(({ method, path }) => {
        const match = phase === 'delta' ? path.includes('/git/blobs/') : method === 'PUT' &&
          (phase === 'checkpoint' ? path.endsWith('/checkpoint.json') : !path.endsWith('/checkpoint.json'));
        if (!failed && match) { failed = true; throw Object.assign(new Error('lost response'), { status: 503 }); }
      });
      await assert.rejects(read(server, 44), /lost response/);
      server.setHook(() => {});
      const before = server.stats().blobs;
      assert.equal(await read(server, 44), true);
      assert.equal(server.stats().blobs - before, phase === 'delta' ? 1 : 0);
    }
  });
}
