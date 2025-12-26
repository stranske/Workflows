Added a case-insensitive allow-change label test to strengthen agents guard label validation while keeping the rest of the suite passing. The new coverage lives in `.github/scripts/__tests__/agents-guard.test.js`.

Tests: `node --test .github/scripts/__tests__/*.test.js`

Next steps:
1. Run/confirm the `Selftest CI` workflow for regression coverage.
2. Update test documentation if you want explicit notes about the new guard coverage.