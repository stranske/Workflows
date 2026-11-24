# Cancelled keepalive reporter evidence

[Original proof packet](original-reporter-proof.tar.gz) contains the 17 files from commit `690ecd34cff68f29c50f65b2ae4ae4dd76970142` at their original repository-relative paths. They include the original commands, both failing and restored reporter runs, JUnit reports, the workflow hashes and the original manifest.
[Browse individual original files](https://github.com/stranske/Workflows/tree/690ecd34cff68f29c50f65b2ae4ae4dd76970142/docs/evidence/keepalive-cancellation-3872).

Run from the checkout root. Set `WORKFLOWS_PYTHON` to the selected Workflows interpreter if the checkout has no `.venv`.

```bash
proof_dir="$(mktemp -d)"
tar -xzpf docs/evidence/keepalive-cancellation-3872/original-reporter-proof.tar.gz -C "$proof_dir"
packet="$proof_dir/docs/evidence/keepalive-cancellation-3872"
"${WORKFLOWS_PYTHON:-.venv/bin/python}" - "$packet" <<'PY'
import hashlib
import json
from pathlib import Path
import stat
import sys

packet = Path(sys.argv[1])
manifest_bytes = (packet / "manifest.json").read_bytes()
manifest_sha256 = "90697f62bfe6612b1e1ffbd90185adb23ebbfe5b96fbd5ce93e20ba58be92be8"
if hashlib.sha256(manifest_bytes).hexdigest() != manifest_sha256:
    raise SystemExit("SHA-256 mismatch for manifest.json")
manifest = json.loads(manifest_bytes)
expected = set(manifest) | {"manifest.json"}
actual = {path.name for path in packet.iterdir()}
if expected - actual:
    raise SystemExit("Missing original files " + ", ".join(sorted(expected - actual)))
if len(expected) != 17 or actual != expected:
    raise SystemExit("Unexpected proof packet inventory")
for name in sorted(expected):
    path = packet / name
    if not path.is_file() or path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != 0o644:
        raise SystemExit("Unexpected file type or mode for " + name)
    if name in manifest and hashlib.sha256(path.read_bytes()).hexdigest() != manifest[name]:
        raise SystemExit("SHA-256 mismatch for " + name)
print("Verified all 17 original files")
PY
```

The recovered `README.md` inside `$packet` gives the original replay commands and results.
