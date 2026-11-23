# Historical formatting and test outputs

The [offline packet](formatting-test-outputs.tar.gz) holds 15 historical outputs. The [validation report](../2026-11-08-validation.md) retains its current log links. The [scope-binding](scope-binding-tests.json) and [payload-path binding](payload-path-binding-tests.json) manifests remain at their original paths.

Run from the Workflows root with the repository Python environment active. The command checks the archive, restores the original paths and verifies every entry. It also copies both original binding manifests and their loose inputs into the recovered tree so the named receipt hashes can be checked offline.

```sh
(
  set -e
  packet=docs/evidence/issue-4369/runtime-4550/formatting-test-outputs.tar.gz
  printf '%s  %s\n' d6c3d36b375226edd5479a494376544c2943a55a0be3b3ac7fd1e15436c69aa3 "$packet" | shasum -a 256 -c -
  recovered=$(mktemp -d)
  tar -xpzf "$packet" -C "$recovered"
  python - "$recovered" <<'PYTHON'
from hashlib import sha256
import json
from pathlib import Path
from shutil import copy2
import sys

source = Path('docs/evidence/issue-4369/runtime-4550')
root = Path(sys.argv[1])
destination = root / source
packet_manifest = json.loads((destination / 'FORMAT-TEST-PACKET.json').read_text())
entries = packet_manifest['entries']
if len(entries) != 15:
    raise SystemExit('Expected 15 original log members')
for row in entries:
    path = root / row['path']
    if sha256(path.read_bytes()).hexdigest() != row['sha256']:
        raise SystemExit(f'Log checksum mismatch: {path}')
    if path.stat().st_mode & 0o777 != 0o644:
        raise SystemExit(f'Log mode mismatch: {path}')
for name, digest in packet_manifest['bound_manifests_sha256'].items():
    original = source / name
    raw = original.read_bytes()
    if sha256(raw).hexdigest() != digest:
        raise SystemExit(f'Manifest checksum mismatch: {original}')
    copy2(original, destination / name)
    for member, expected in json.loads(raw)['evidence_sha256'].items():
        if Path(member).name != member:
            raise SystemExit(f'Unexpected manifest member path: {member}')
        target = destination / member
        if not target.exists():
            copy2(source / member, target)
        if sha256(target.read_bytes()).hexdigest() != expected:
            raise SystemExit(f'Bound digest mismatch: {target}')
print(f'Verified 15 logs and both original manifests in {root}')
PYTHON
)
```

## Original publication links

- [coding-stall-evidence-tests.log](https://github.com/stranske/Workflows/blob/b28068cc84089b55e2b521c0b09ac6c744990c8b/docs/evidence/issue-4369/runtime-4550/coding-stall-evidence-tests.log)
- [delivery-lifecycle-black.log](https://github.com/stranske/Workflows/blob/2571ae7b91538b535c1b817c3c92c468e3d80ccf/docs/evidence/issue-4369/runtime-4550/delivery-lifecycle-black.log)
- [delivery-lifecycle-tests.log](https://github.com/stranske/Workflows/blob/2571ae7b91538b535c1b817c3c92c468e3d80ccf/docs/evidence/issue-4369/runtime-4550/delivery-lifecycle-tests.log)
- [downstream-followup-black-supported.log](https://github.com/stranske/Workflows/blob/482ba34d49f0f91e163b8e8060fb13c3996c9630/docs/evidence/issue-4369/runtime-4550/downstream-followup-black-supported.log)
- [downstream-followup-black.log](https://github.com/stranske/Workflows/blob/482ba34d49f0f91e163b8e8060fb13c3996c9630/docs/evidence/issue-4369/runtime-4550/downstream-followup-black.log)
- [downstream-followup-tests.log](https://github.com/stranske/Workflows/blob/482ba34d49f0f91e163b8e8060fb13c3996c9630/docs/evidence/issue-4369/runtime-4550/downstream-followup-tests.log)
- [downstream-refresh-black.log](https://github.com/stranske/Workflows/blob/e5e6aeb00c3cfb183ce59027365483ff1f1462d9/docs/evidence/issue-4369/runtime-4550/downstream-refresh-black.log)
- [downstream-refresh-tests.log](https://github.com/stranske/Workflows/blob/e5e6aeb00c3cfb183ce59027365483ff1f1462d9/docs/evidence/issue-4369/runtime-4550/downstream-refresh-tests.log)
- [payload-path-binding-black-supported.log](https://github.com/stranske/Workflows/blob/0a05390816ca7ed3a5c73ce6edf9aa65065d2d87/docs/evidence/issue-4369/runtime-4550/payload-path-binding-black-supported.log)
- [payload-path-binding-black.log](https://github.com/stranske/Workflows/blob/0a05390816ca7ed3a5c73ce6edf9aa65065d2d87/docs/evidence/issue-4369/runtime-4550/payload-path-binding-black.log)
- [scope-binding-black-one-worker.log](https://github.com/stranske/Workflows/blob/69c8345dd1fd5744d0fd5312a7ef55c88dc66f7e/docs/evidence/issue-4369/runtime-4550/scope-binding-black-one-worker.log)
- [scope-binding-black-supported-2.log](https://github.com/stranske/Workflows/blob/69c8345dd1fd5744d0fd5312a7ef55c88dc66f7e/docs/evidence/issue-4369/runtime-4550/scope-binding-black-supported-2.log)
- [scope-binding-black-supported-3.log](https://github.com/stranske/Workflows/blob/69c8345dd1fd5744d0fd5312a7ef55c88dc66f7e/docs/evidence/issue-4369/runtime-4550/scope-binding-black-supported-3.log)
- [scope-binding-black-supported.log](https://github.com/stranske/Workflows/blob/69c8345dd1fd5744d0fd5312a7ef55c88dc66f7e/docs/evidence/issue-4369/runtime-4550/scope-binding-black-supported.log)
- [scope-binding-black.log](https://github.com/stranske/Workflows/blob/69c8345dd1fd5744d0fd5312a7ef55c88dc66f7e/docs/evidence/issue-4369/runtime-4550/scope-binding-black.log)
