# Missing and opaque pytest launcher admission

Related #3743; broader coverage work stays open.

The current helper is still first in the last400 scripts-touching commit ranking:
73 repair-subject matches and82 touches. These are churn/repair proxies, not
verified escaped-defect counts. The matched current nine-module baseline left
lines355/358 and their branches uncovered. A missing pytest executable or a
shell launcher with no Python identity must not authorize repair of the active
interpreter's PyYAML environment.

Four new root/template cases use a private PATH, genuine missing executable and
executable shell script, real shutil.which and real shebang parsing. Production
code, consumer template, workflow/routing settings, exclusions and633 tracked
historical evidence files are unchanged.

Validation used /opt/anaconda3/bin/python3 (Python3.12.2, macOS26.6.2):

- Named new module:4PASS.
- Identical nine existing helper/replay modules:312PASS baseline; with only the
  new module added:316PASS. Exactly4 new nodes, no removed/changed old outcomes
  and no covered-line/branch regressions.
- Root helper:581→583 of591 statements and249→251 of262 branches; zero exclusions.
  These focused measurements are not repository-wide90% coverage.
- Each named new case ran against its corresponding actual production mutation
  (return False→True): assertionREDexit1, exact byte restorationGREENexit0,
  one case and zero errors/skips. Root and consumer copies were mutated only in
  disposable private directories, never the checkout.
- Existing output reuse was refused before mutation;17 proof files remained
  byte-identical.
- Full repositoryBlack (708files), focusedRuff, strict template completeness and
  git diff --check passed.

Replay from the repository or any working directory:

```bash
/opt/anaconda3/bin/python3 docs/evidence/issue-3743/launcher-admission/replay.py   --output /tmp/new-launcher-admission-proof
```

proof.tar.gz retains35 raw members: matched command argv/cwd/exits, full console,
JUnit and coverageJSON plus raw coverage databases; four mutation-pair receipts
and logs/JUnit; reuse, focused and validation records; fresh ranking. manifest.json
binds every decoded member and committed source/test/proof file with SHA256.
summary.json records the exact baseline/environment/counts/coverage universe.

Hosted CI, expected-check topology, review-thread disposition, seven-minute
exact-head floor, merge and actual provider comparison remain future delivery
gates. Earlier3832/3838 CONCERNS remain unchanged. This chunk proves no native
acceptance, installed deployment, providerPASS or whole-source completion.
