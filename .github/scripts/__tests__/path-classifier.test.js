'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  DEFAULT_CATEGORIES,
  classifyFiles,
  globToRegExp,
  loadDeliveryContract,
  matchesAny,
  parseClassificationConfig,
  stableDeliverySealStatus,
} = require('../../actions/path-classifier/classify.js');
const deliveryContract = require('../sync_pr_lease_contract.js');

const CONFIG = { categories: DEFAULT_CATEGORIES };

function outputsFor(files, options) {
  return classifyFiles(files, CONFIG, options).outputs;
}

test('glob matcher handles root and nested patterns', () => {
  assert.match('README.md', globToRegExp('*.md'));
  assert.doesNotMatch('docs/README.md', globToRegExp('*.md'));
  assert.equal(matchesAny('pkg/module.py', ['**/*.py']), true);
  assert.equal(matchesAny('module.py', ['**/*.py']), true);
  assert.equal(matchesAny('.github/actions/path-classifier/action.yml', ['.github/actions/**']), true);
});

test('classifies docs-only changes when every path matches docs rules', () => {
  const outputs = outputsFor(['README.md', 'docs/usage.md']);
  assert.equal(outputs['is-docs-only'], 'true');
  assert.equal(outputs['is-python-code'], 'false');
  assert.equal(outputs['is-security-relevant'], 'false');
});

test('classifies python code changes', () => {
  const outputs = outputsFor(['src/app.py', 'requirements-dev.txt']);
  assert.equal(outputs['is-python-code'], 'true');
  assert.equal(outputs['is-docs-only'], 'false');
});

test('classifies workflow and security relevant changes', () => {
  const outputs = outputsFor(['.github/workflows/pr-00-gate.yml']);
  assert.equal(outputs['is-workflow-change'], 'true');
  assert.equal(outputs['is-security-relevant'], 'true');
});

test('classifies security relevant tool and pyproject changes', () => {
  const outputs = outputsFor(['tools/enforce_gate_branch_protection.py', 'pyproject.toml']);
  assert.equal(outputs['is-security-relevant'], 'true');
  assert.equal(outputs['is-python-code'], 'true');
});

test('classifies template changes', () => {
  const outputs = outputsFor(['templates/consumer-repo/.github/workflows/pr-00-gate.yml']);
  assert.equal(outputs['is-template-change'], 'true');
  assert.equal(outputs['is-workflow-change'], 'false');
});

test('classifies test-only changes when every path is a test', () => {
  const outputs = outputsFor([
    'tests/workflows/test_gate.py',
    '.github/scripts/__tests__/path-classifier.test.js',
  ]);
  assert.equal(outputs['is-test-only'], 'true');
  assert.equal(outputs['is-python-code'], 'true');
});

test('mixed docs and code changes are not docs-only or test-only', () => {
  const outputs = outputsFor(['docs/usage.md', 'scripts/sync_dev_dependencies.py']);
  assert.equal(outputs['is-docs-only'], 'false');
  assert.equal(outputs['is-test-only'], 'false');
  assert.equal(outputs['is-python-code'], 'true');
  assert.equal(outputs['is-security-relevant'], 'true');
});

test('empty diff does not enable categories', () => {
  const outputs = outputsFor([]);
  assert.equal(outputs['is-docs-only'], 'false');
  assert.equal(outputs['is-python-code'], 'false');
  assert.equal(outputs['is-workflow-change'], 'false');
  assert.equal(outputs['is-security-relevant'], 'false');
  assert.equal(outputs['is-template-change'], 'false');
  assert.equal(outputs['is-test-only'], 'false');
  assert.equal(outputs['affected-consumers'], '[]');
});

test('force-full override enables every category output', () => {
  const outputs = outputsFor(['README.md'], { forceFull: true });
  assert.equal(outputs['is-docs-only'], 'true');
  assert.equal(outputs['is-python-code'], 'true');
  assert.equal(outputs['is-workflow-change'], 'true');
  assert.equal(outputs['is-security-relevant'], 'true');
  assert.equal(outputs['is-template-change'], 'true');
  assert.equal(outputs['is-test-only'], 'true');
});

test('parses classification YAML config', () => {
  const parsed = parseClassificationConfig(`
categories:
  docs-only:
    require-all: true
    paths:
      - docs/**
      - "*.md"
  python-code:
    require-all: false
    paths: ["**/*.py", pyproject.toml]
`);
  assert.deepEqual(parsed.categories['docs-only'], {
    requireAll: true,
    paths: ['docs/**', '*.md'],
  });
  assert.deepEqual(parsed.categories['python-code'], {
    requireAll: false,
    paths: ['**/*.py', 'pyproject.toml'],
  });
});

function deliveryContext(record, { branch = 'sync/workflows-delivery', fork = false } = {}) {
  return {
    event_name: 'pull_request',
    event: {
      pull_request: {
        body: deliveryContract.formatDeliveryRecord(record),
        head: {
          ref: branch,
          sha: 'head-abc',
          repo: { full_name: fork ? 'attacker/Ready' : 'stranske/Ready' },
        },
        base: {
          sha: 'trusted-base-sha',
          repo: { full_name: 'stranske/Ready' },
        },
      },
    },
  };
}

const deliveryRecord = {
  schema: 'sync-pr-delivery-record/v1',
  durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
  plan_id: 'plan-abc',
  generation: 'generation-abc',
  repository: 'stranske/Ready',
  desired_tree_hash: 'tree-abc',
  source_commit: 'source-abc',
  lease_expires_at: '2099-08-14T00:00:00Z',
  predecessor_prs: [],
  successor_prs: [],
  delivery_state: 'staging',
};

test('custom Gate classifier rejects an unsealed stable delivery', () => {
  assert.deepEqual(
    stableDeliverySealStatus(deliveryContext(deliveryRecord), {
      contract: deliveryContract,
      now: '2026-08-12T00:00:00Z',
    }),
    { required: true, valid: false, reason: 'delivery_not_sealed:staging' },
  );
});

test('stable delivery loads its seal contract from the exact trusted base SHA', () => {
  let requested = null;
  const contractSource = require('node:fs').readFileSync(
    require('node:path').join(__dirname, '..', 'sync_pr_lease_contract.js'),
    'utf8',
  );
  const contract = loadDeliveryContract(deliveryContext(deliveryRecord), {
    readTrustedContract: (ref, contractPath) => {
      requested = { ref, contractPath };
      return contractSource;
    },
  });

  assert.deepEqual(requested, {
    ref: 'trusted-base-sha',
    contractPath: '.github/scripts/sync_pr_lease_contract.js',
  });
  assert.equal(contract.mergeEligibility(deliveryRecord, { requireSealed: true }).eligible, false);
});

test('stable delivery fails closed when the trusted base contract is unavailable', () => {
  const contract = loadDeliveryContract(deliveryContext(deliveryRecord), {
    readTrustedContract: () => {
      throw new Error('base object unavailable');
    },
  });
  assert.equal(contract, null);
});

test('custom Gate classifier accepts only the sealed exact head', () => {
  const sealed = {
    ...deliveryRecord,
    delivery_state: 'sealed',
    review_started_at: '2026-08-12T00:00:00Z',
    sealed_at: '2026-08-12T00:15:00Z',
    sealed_head_sha: 'head-abc',
  };
  assert.deepEqual(
    stableDeliverySealStatus(deliveryContext(sealed), {
      contract: deliveryContract,
      now: '2026-08-12T00:20:00Z',
    }),
    { required: true, valid: true, reason: 'current_unexpired' },
  );
  assert.equal(
    stableDeliverySealStatus(deliveryContext(sealed, { fork: true }), {
      contract: deliveryContract,
      now: '2026-08-12T00:20:00Z',
    }).valid,
    false,
  );
});
