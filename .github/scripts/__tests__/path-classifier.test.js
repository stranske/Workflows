'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  DEFAULT_CATEGORIES,
  classifyFiles,
  fetchBaseRef,
  globToRegExp,
  isAddOnlyContractDiff,
  isStableDeliveryPullRequest,
  listChangedFiles,
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
    isBootstrapAddition: () => false,
  });
  assert.equal(contract, null);
});

test('stable delivery bootstraps an add-only contract when the trusted base predates it', () => {
  const contractSource = require('node:fs').readFileSync(
    require('node:path').join(__dirname, '..', 'sync_pr_lease_contract.js'),
    'utf8',
  );
  assert.equal(contractSource.endsWith('\n'), true);
  const observed = {};
  const contract = loadDeliveryContract(deliveryContext(deliveryRecord), {
    readTrustedContract: () => {
      throw new Error('contract absent from base');
    },
    isBootstrapAddition: (baseSha, headSha, contractPath) => {
      Object.assign(observed, { baseSha, headSha, contractPath });
      return true;
    },
    readBootstrapContract: (ref, contractPath) => {
      observed.bootstrapRef = ref;
      observed.bootstrapPath = contractPath;
      return contractSource;
    },
  });

  assert.deepEqual(observed, {
    baseSha: 'trusted-base-sha',
    headSha: 'head-abc',
    contractPath: '.github/scripts/sync_pr_lease_contract.js',
    bootstrapRef: 'head-abc',
    bootstrapPath: '.github/scripts/sync_pr_lease_contract.js',
  });
  assert.equal(contract.mergeEligibility(deliveryRecord, { requireSealed: true }).eligible, false);
});

test('consumer template preserves raw bootstrap contract bytes', () => {
  const templateClassifier = require('node:fs').readFileSync(
    require('node:path').join(
      __dirname,
      '..',
      '..',
      '..',
      'templates',
      'consumer-repo',
      '.github',
      'actions',
      'path-classifier',
      'classify.js',
    ),
    'utf8',
  );
  const rawContractReader = templateClassifier.match(
    /function readContractAtRef\(ref, contractPath\) \{[\s\S]*?\n\}/,
  );
  assert.ok(rawContractReader, 'template must define readContractAtRef');
  assert.match(
    rawContractReader[0],
    /return readGit\(\['show', `\$\{ref\}:\$\{contractPath\}`\]\);/,
  );
  assert.doesNotMatch(rawContractReader[0], /\.trim\(/);
  assert.match(templateClassifier, /function runGit\(args\) \{\n  return readGit\(args\)\.trim\(\);/);
});

test('stable delivery bootstrap fails closed without an exact head SHA', () => {
  const context = deliveryContext(deliveryRecord);
  context.event.pull_request.head.sha = '';
  let bootstrapRead = false;
  const contract = loadDeliveryContract(context, {
    readTrustedContract: () => {
      throw new Error('contract absent from base');
    },
    isBootstrapAddition: () => true,
    readBootstrapContract: () => {
      bootstrapRead = true;
      return '';
    },
  });

  assert.equal(contract, null);
  assert.equal(bootstrapRead, false);
});

test('stable delivery bootstrap fails closed when the exact head contract is unreadable', () => {
  const contract = loadDeliveryContract(deliveryContext(deliveryRecord), {
    readTrustedContract: () => {
      throw new Error('contract absent from base');
    },
    isBootstrapAddition: () => true,
    readBootstrapContract: () => {
      throw new Error('head object unavailable');
    },
  });

  assert.equal(contract, null);
});

test('stable delivery bootstrap rejects a modified contract from the PR head', () => {
  const contract = loadDeliveryContract(deliveryContext(deliveryRecord), {
    readTrustedContract: () => {
      throw new Error('contract absent from base');
    },
    isBootstrapAddition: () => true,
    readBootstrapContract: () => 'module.exports = { mergeEligibility: () => ({ eligible: true }) };',
  });

  assert.equal(contract, null);
});

test('stable delivery bootstrap recognizes only an exact added contract path', () => {
  const contractPath = '.github/scripts/sync_pr_lease_contract.js';
  assert.equal(isAddOnlyContractDiff(`A\t${contractPath}`, contractPath), true);
  assert.equal(isAddOnlyContractDiff(`M\t${contractPath}`, contractPath), false);
  assert.equal(isAddOnlyContractDiff(`R100\told.js\t${contractPath}`, contractPath), false);
  assert.equal(isAddOnlyContractDiff(`A\t${contractPath}.bak`, contractPath), false);
});

test('stable delivery bootstrap rejects fork heads even when they add the contract', () => {
  let bootstrapRead = false;
  const contract = loadDeliveryContract(
    deliveryContext(deliveryRecord, { fork: true }),
    {
      readTrustedContract: () => {
        throw new Error('contract absent from base');
      },
      isBootstrapAddition: () => true,
      readBootstrapContract: () => {
        bootstrapRead = true;
        return '';
      },
    },
  );
  assert.equal(contract, null);
  assert.equal(bootstrapRead, false);
});

test('stable delivery fetch includes the exact same-repository head for shallow PR checkouts', () => {
  const calls = [];
  fetchBaseRef('origin/main', deliveryContext(deliveryRecord), (args) => {
    calls.push(args);
    return '';
  });
  assert.deepEqual(calls, [
    [
      'fetch',
      '--no-tags',
      '--depth=1',
      'origin',
      'main',
      'trusted-base-sha',
      'head-abc',
    ],
  ]);

  const forkCalls = [];
  fetchBaseRef('origin/main', deliveryContext(deliveryRecord, { fork: true }), (args) => {
    forkCalls.push(args);
    return '';
  });
  assert.equal(forkCalls[0].includes('head-abc'), false);

  const ordinaryCalls = [];
  fetchBaseRef(
    'origin/main',
    deliveryContext(deliveryRecord, { branch: 'feature/example' }),
    (args) => {
      ordinaryCalls.push(args);
      return '';
    },
  );
  assert.equal(ordinaryCalls[0].includes('head-abc'), false);
});

test('stable delivery reuses its trusted-base fetch for changed-file classification', () => {
  const context = deliveryContext(deliveryRecord);
  let fetches = 0;
  const options = {
    baseRef: 'origin/main',
    githubContext: { ...context, sha: 'head-abc' },
    fetchBase: () => {
      fetches += 1;
    },
    diffGit: () => '',
  };

  assert.equal(isStableDeliveryPullRequest(context), true);
  listChangedFiles({ ...options, baseAlreadyFetched: true });
  assert.equal(fetches, 0);

  const ordinaryContext = deliveryContext(deliveryRecord, { branch: 'feature/example' });
  assert.equal(isStableDeliveryPullRequest(ordinaryContext), false);
  listChangedFiles({
    ...options,
    githubContext: { ...ordinaryContext, sha: 'head-abc' },
    baseAlreadyFetched: false,
  });
  assert.equal(fetches, 1);
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
