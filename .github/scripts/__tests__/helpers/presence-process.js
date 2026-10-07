'use strict';

// Each child imports production defaults. Only the parent owns durable server
// state, so neither require.cache nor process-local memoization can prove reuse.
let next = 0;
const pending = new Map();
process.on('message', (message) => {
  const handlers = pending.get(message.id);
  if (!handlers) return;
  pending.delete(message.id);
  if (message.error) handlers.reject(Object.assign(new Error(message.error.message), message.error));
  else handlers.resolve(message.value);
});
const request = (method, path, body) => new Promise((resolve, reject) => {
  const id = ++next;
  pending.set(id, { resolve, reject });
  process.send({ id, method, path, body });
});
const { replayReporterAuthority } = require(process.argv[2]);
replayReporterAuthority({ github: {}, context: { repo: { owner: 'owner', repo: 'repo' } },
  prNumber: Number(process.argv[3]), makeRequest: () => request })
  .then((value) => process.send({ done: true, value }))
  .catch((error) => process.send({ done: true, error: error.message }))
  .finally(() => process.disconnect());
