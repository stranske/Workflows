# Issue 4097 deliberate-break receipt

Command (source and consumer mirror exercised by one regression):

```sh
node --test --test-name-pattern="standard discovery retrieves 10 runs across 2 pages" .github/scripts/__tests__/agents-verifier-context.test.js
```

- Default 100-run limit: exit 0.
- Deliberately restored `DEFAULT_EVIDENCE_RUN_LIMIT = 5` in source and template: exit 1.
- Failure: artifacts incomplete, `workflow run discovery ... exceeded the bounded result limit`;
  ten runs over two pages cannot be inspected within the old five-run limit.
- Restored 100-run source and template bytes in a `finally` block: exit 0.

This is local regression evidence. Production retrieval availability and issue
closure counts remain unmeasured until merge + 48 hours.
