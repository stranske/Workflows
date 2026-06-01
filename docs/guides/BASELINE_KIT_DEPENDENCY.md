# Declaring the `app-baseline-kit` Dependency

> How every `stranske/*` consumer repo should pull in the shared
> `app-baseline-kit` package (the `baseline_kit` import) that lives in this
> monorepo under `packages/app-baseline-kit`.

This guide is the **catalog of accepted patterns** for the baseline-kit
dependency across the fleet. It complements the operational walkthrough in
[`ops/CONSUMER_REPO_MAINTENANCE.md` → Monorepo Package Dependencies](../ops/CONSUMER_REPO_MAINTENANCE.md#monorepo-package-dependencies-app-baseline-kit),
which explains the `uv` "conflicting URLs" failure class and the no-emit fix in
step-by-step form, and is reached from
[`INTEGRATION_GUIDE.md`](../INTEGRATION_GUIDE.md). Read that section first if you
are debugging a CI install failure; read this guide when you are deciding **which
pattern a repo should adopt** and why the fleet has more than one.

## Policy (read this first)

- `app-baseline-kit` is an **internal, unpublished** package. It is not on PyPI;
  it is consumed straight from this monorepo via a PEP 508 direct git reference
  (`name @ git+https://github.com/stranske/Workflows.git#subdirectory=packages/app-baseline-kit`).
  Because it is URL-referenced, it is **pinned by URL, not by a `==` version** —
  it never appears as a normal pinned line that a lock version-check should expect.
- **The default is Pattern A** (unpinned `@main` in `pyproject.toml` +
  `[tool.uv.pip] no-emit-package`). Adopt Pattern A unless a real, repo-specific
  constraint blocks it.
- **Multiple patterns are acceptable.** Working repos that use Pattern B
  (custom-build-backend, lock-only) or vendoring are **not** to be force-migrated
  to Pattern A. Each non-default repo carries a one-page justification in its own
  `docs/baseline-kit-dependency.md` naming the concrete constraint.
- **Pattern C (frozen SHA) is deprecated.** A `pyproject.toml` that pins
  `app-baseline-kit @ git+...@<sha>#...` is a stopgap, not a target state. Any
  repo on Pattern C must migrate to Pattern A (it tracks Workflows `main` and
  removes the SHA from the loop). See [Fixing a Pattern C repo](#fixing-a-pattern-c-repo-frozen-sha--pattern-a).
- `baseline_kit` ships a **`py.typed` marker** (Workflows PR #2204, merged), so
  it is a typed package. Editable/git installs still may not expose stubs to a
  strict `mypy` run depending on how the consumer resolves it; per-repo
  `mypy` overrides for `import-untyped` are acceptable and do not change the
  dependency pattern.

## The patterns

### Pattern A — `pyproject` `@main`, excluded from the lock (DEFAULT)

**Reference implementation: `trip-planner`.**

```toml
# pyproject.toml
[project.optional-dependencies]
dev = [
    "app-baseline-kit @ git+https://github.com/stranske/Workflows.git#subdirectory=packages/app-baseline-kit",
]

# Do not freeze a commit SHA for the monorepo package in requirements.lock.
[tool.uv.pip]
no-emit-package = ["app-baseline-kit"]
```

**When to use:** any repo whose build backend can serialize a URL dependency in
extras metadata (i.e. plain `setuptools.build_meta`) and that wants to track
Workflows `main` automatically. This is the right answer for a pilot/unversioned
package.

**Mechanism:** the unpinned `@main` URL resolves to Workflows `main` HEAD at
install time. `[tool.uv.pip] no-emit-package` keeps `uv pip compile` from
freezing a commit SHA into `requirements.lock`, so the lock and the editable
project never disagree about the URL. The editable install
(`pip install -e .[dev]` / `uv pip install -e .`) resolves the package directly
from `@main`. If the repo has `tests/test_dependency_version_alignment.py`, it
must subtract the `no-emit-package` names from the set it expects to find pinned
in the lock (drive it from the config, not a hardcoded name).

**Tradeoffs:** tracks `main` automatically (good for an unversioned package), and
the "conflicting URLs for package `app-baseline-kit`" failure class is gone
permanently — there is no frozen SHA to refresh. The cost is that the exact
baseline-kit commit used in CI is not recorded in the lock; reproducibility of
*that one package* depends on `main` HEAD at install time. Acceptable while the
package is unversioned; revisit once it is tagged/released.

> **Pattern A variant (lock-SHA, no no-emit):** `Pension-Data` declares `@main`
> in `pyproject.toml` but does **not** use `no-emit-package`, so `uv pip compile`
> records a SHA for the package in `requirements.lock` and CI installs
> `-r requirements.lock`. This is a working, accepted variant: developers pick up
> new `main` features when they regenerate the lock, and CI runs reproducibly
> against the recorded SHA. It is **not** Pattern C — the `pyproject` source of
> truth stays unpinned `@main`. The cost is lock churn whenever the lock is
> regenerated against an advanced `main`; if that churn becomes a conflict
> source, add `no-emit-package` to move to canonical Pattern A.

### Pattern B — lock-only / `requirements-baseline.txt` (custom build backend)

**Reference implementation: `Travel-Plan-Permission` (TPP).**

**When to use:** only when the repo uses a **custom build backend** that cannot
serialize a PEP 508 `name @ git+url` direct reference carrying an extra marker
into valid `Requires-Dist` metadata. TPP's `tp_build_backend`
(`tools/build_backend/tp_build_backend.py`) is the canonical case: declaring
`app-baseline-kit` in `[project.optional-dependencies]` produces
`Requires-Dist: app-baseline-kit @ git+...; extra == "dev"`, which fails with
*"invalid metadata: Expected semicolon (after URL and whitespace)"* and breaks
every `pip install -e .`.

**Mechanism:** the dependency is kept **out of `pyproject.toml`** entirely. It
lives in `tests/baseline/requirements-baseline.txt` (the canonical source for
local runs) and is compiled into `requirements.lock`. CI installs it via the
reusable Python job's `-r requirements.lock`. The lock (and baseline txt) are
regenerated together by the repo's dependency-refresh workflow.

**Tradeoffs:** the only viable pattern under a metadata-restrictive custom
backend. It does not auto-track `main` (the lock carries a SHA), so picking up
new baseline-kit features requires a lock regeneration. Do not migrate a Pattern B
repo to Pattern A unless its build backend changes to one that can serialize URL
deps in extras.

### Pattern C — frozen SHA in `pyproject.toml` (DEPRECATED — must migrate)

**Current instance: `learning-management-system` (LMS).**

```toml
# DEPRECATED — do not adopt for new repos.
"app-baseline-kit @ git+https://github.com/stranske/Workflows.git@13f94883220bbfb0ca69a4666fb44a49e0ae8172#subdirectory=packages/app-baseline-kit"
```

**Why it exists:** it is a stopgap for the `uv` conflicting-URL error. When
`pyproject.toml` and `requirements.lock` disagreed on the URL form (one with an
`@<sha>` fragment, one without), `uv` refused to resolve. Pinning `pyproject` to
the exact SHA already in the lock made both sources agree, so installs became
deterministic instead of cache-dependent.

**Why it is deprecated:** it freezes baseline-kit to a stale commit, severs `main`
tracking, and re-introduces a SHA that someone must remember to bump. The
no-emit approach (Pattern A) eliminates the same conflict *permanently* without a
frozen SHA, so Pattern C buys nothing Pattern A does not. **Migrate every Pattern
C repo to Pattern A.**

#### Fixing a Pattern C repo (frozen SHA → Pattern A)

Do exactly what `trip-planner` does:

1. In `pyproject.toml`, **unpin to `@main`** — drop the `@<sha>` fragment so the
   reference reads
   `app-baseline-kit @ git+https://github.com/stranske/Workflows.git#subdirectory=packages/app-baseline-kit`.
2. Add the package to the no-emit list:
   ```toml
   [tool.uv.pip]
   no-emit-package = ["app-baseline-kit"]
   ```
3. **Regenerate `requirements.lock`** with the repo's documented `uv pip compile`
   command (e.g. `uv pip compile pyproject.toml --extra dev --universal -o requirements.lock`)
   and confirm `app-baseline-kit` is **excluded** from the lock.
4. Ensure `tests/test_dependency_version_alignment.py` **subtracts the
   `no-emit-package` names** from the expected-in-lock set (drive it from the
   `[tool.uv.pip].no-emit-package` config, not a hardcoded name).
5. Verify: a clean install (`uv pip install -e .[dev]` or the repo's documented
   install) succeeds, `tests/test_dependency_version_alignment.py` passes, and
   the `tests/baseline` suite passes.

These are per-repo `pyproject.toml` / `requirements.lock` / test changes — they
are **not** synced template files.

### Vendoring (special case — not a numbered pattern)

**Instance: `Inv-Man-Intake`.** When the consumed surface is a tiny,
zero-runtime-dependency test harness, a repo may vendor a copy of the module
(`src/baseline_kit/__init__.py`) and remove the git reference entirely,
declaring `baseline_kit` as first-party in `.project_modules.txt`. This trades
`main` tracking for zero lock churn and zero external-repo coupling. It is a
deliberate decoupling: if the upstream `baseline_kit` changes, the vendored copy
must be synced manually. Only appropriate for a small, stable, dependency-free
harness.

## Per-repo mapping

| Repo | Build backend | Pattern | In lock? | Tracks `main`? | Gets `baseline_kit` at test time via |
|------|---------------|---------|----------|----------------|--------------------------------------|
| `trip-planner` | setuptools | **A** (reference) | excluded (no-emit) | yes | editable install of `@main` |
| `Counter_Risk` | setuptools | **A** (+no-emit) | excluded (no-emit) | yes | `pip install -e .[dev]` from `@main` |
| `Trend_Model_Project` | setuptools | **A** (unpinned) | absent | yes | `pip install -e .[dev]` from `@main` |
| `Portable-Alpha-Extension-Model` | setuptools | **A** (unpinned `@main`) | absent | yes | `pip install -e .` from `@main` (PEP 508 URL-pinned, not version-pinned) |
| `Pension-Data` | setuptools | **A variant** (`@main` in pyproject, SHA in lock) | SHA `13f94883…` | yes (on lock regen) | CI installs `-r requirements.lock` (pinned SHA) |
| `Travel-Plan-Permission` | custom (`tp_build_backend`) | **B** (lock-only) | SHA `13f94883…` | no | CI `-r requirements.lock`; local `requirements-baseline.txt` |
| `learning-management-system` | setuptools | **C** (frozen SHA — migrate to A) | SHA `13f94883…` | no | `-r requirements.lock` (pinned SHA) |
| `Inv-Man-Intake` | setuptools | **Vendored** | absent | no | local `src/baseline_kit/` (first-party in `.project_modules.txt`) |

## How to choose (decision order)

1. **Custom build backend that cannot serialize URL deps in extras metadata?**
   → **Pattern B** (keep the dep out of `pyproject.toml`; live in
   `requirements.lock` + `requirements-baseline.txt`).
2. **Tiny, zero-dependency harness where decoupling from upstream is desirable?**
   → **Vendoring** (with `.project_modules.txt` first-party declaration).
3. **Otherwise (plain `setuptools`)** → **Pattern A**: unpinned `@main` in
   `pyproject.toml` + `[tool.uv.pip] no-emit-package = ["app-baseline-kit"]`,
   and subtract no-emit names in the dependency-alignment test.
4. **Never adopt Pattern C** (frozen SHA in `pyproject.toml`) for new repos, and
   migrate existing Pattern C repos using the steps above.

## See also

- [`ops/CONSUMER_REPO_MAINTENANCE.md` → Monorepo Package Dependencies](../ops/CONSUMER_REPO_MAINTENANCE.md#monorepo-package-dependencies-app-baseline-kit)
  — the conflict mechanics and no-emit fix in operational detail.
- [`INTEGRATION_GUIDE.md`](../INTEGRATION_GUIDE.md) — how consumer repos integrate
  with reusable workflows and the monorepo.
- `packages/app-baseline-kit/` — the package itself (ships `py.typed`, PR #2204).
