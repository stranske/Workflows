# Recover the historical partial-mirror evidence

The [original incident report](README.md) remains at its published path. The [archive](partial-mirror.tar.gz) contains the 23 companion files at their original relative paths. For current setup, see the [repo-review procedure](../../../ops/REPO_REVIEW_PROCESS.md#optional-local-batch-authoring). Run the commands below from this directory with the repository Python environment active.

```sh
set -e
printf '%s  %s\n' c9840f55a61fbd0ed637dffa023a31d2575dd13f07336595e27679e5d2c30679 partial-mirror.tar.gz | shasum -a 256 -c -
recovery=$(mktemp -d)
tar -xpzf partial-mirror.tar.gz -C "$recovery"
python - "$recovery" <<'PYTHON'
from hashlib import sha256
from pathlib import Path
import json
import sys
root = Path(sys.argv[1])
entries = json.loads((root / 'MANIFEST.json').read_text())['entries']
if len(entries) != 23:
    raise SystemExit('Expected 23 original members')
for entry in entries:
    p = root / entry['path']
    if sha256(p.read_bytes()).hexdigest() != entry['sha256']:
        raise SystemExit(f'Checksum mismatch: {p}')
    if p.stat().st_mode & 0o777 != int(entry['mode'], 8) & 0o777:
        raise SystemExit(f'Mode mismatch: {p}')
print(root)
PYTHON
```

## Immutable per-member sources

- [black-check-responsive.txt](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/black-check-responsive.txt)
- [black-runtime.txt](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/black-runtime.txt)
- [fallback-proof.json](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/fallback-proof.json)
- [fallback-red.txt](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/fallback-red.txt)
- [fallback-restored-green.txt](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/fallback-restored-green.txt)
- [partial-mirror-0.json](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/partial-mirror-0.json)
- [partial-mirror-1.json](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/partial-mirror-1.json)
- [pytest-green.txt](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/pytest-green.txt)
- [role-case-0/0.md](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/role-case-0/0.md)
- [role-case-0/1.md](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/role-case-0/1.md)
- [role-case-0/2.md](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/role-case-0/2.md)
- [role-case-0/role-manifest.json](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/role-case-0/role-manifest.json)
- [role-case-0/upload-authoring.json](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/role-case-0/upload-authoring.json)
- [role-case-1/0.md](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/role-case-1/0.md)
- [role-case-1/1.md](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/role-case-1/1.md)
- [role-case-1/2.md](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/role-case-1/2.md)
- [role-case-1/role-manifest.json](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/role-case-1/role-manifest.json)
- [role-case-1/upload-authoring.json](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/role-case-1/upload-authoring.json)
- [role-case-2/0.md](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/role-case-2/0.md)
- [role-case-2/1.md](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/role-case-2/1.md)
- [role-case-2/2.md](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/role-case-2/2.md)
- [role-case-2/role-manifest.json](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/role-case-2/role-manifest.json)
- [role-case-2/upload-authoring.json](https://github.com/stranske/Workflows/blob/dcd9db6c72a9954c8f57bc98093ff10eda71836d/docs/evidence/issue-4051/partial-mirror/role-case-2/upload-authoring.json)
