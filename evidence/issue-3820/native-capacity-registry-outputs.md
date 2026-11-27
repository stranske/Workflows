# Native capacity registry verification outputs

The [repair report](native-capacity-registry-repair.md) records the October registry repair. Its 34 command transcripts and JUnit reports are grouped in [one archive](native-capacity-registry-outputs.tar.xz). The [original directory](https://github.com/stranske/Workflows/tree/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820) provides individual file links. The [verification manifest](native-capacity-registry-verification.json), two proof files and preservation inventory retain their original locations.

From the repository root, verify every member against the original manifest.

```sh
python - <<'PYTHON'
from hashlib import sha256
import json
from pathlib import Path
import sys
import tarfile

base = Path('evidence/issue-3820')
manifest = json.loads((base / 'native-capacity-registry-verification.json').read_text())
outputs = {p: h for p, h in manifest['artifacts'].items() if p.endswith(('.xml', '.txt'))}
with tarfile.open(base / 'native-capacity-registry-outputs.tar.xz', 'r:xz') as archive:
    members = archive.getmembers()
    if len(outputs) != 34 or len(members) != 34 or {m.name for m in members} != set(outputs):
        sys.exit('Archive inventory differs from the 34 recorded outputs')
    for m in members:
        if not m.isfile() or m.mode != 0o644 or sha256(archive.extractfile(m).read()).hexdigest() != outputs[m.name]:
            sys.exit(f'Archive member changed: {m.name}')
print('Verified all 34 recorded outputs')
PYTHON
```

To use the original paths, extract the archive to a scratch directory.

```sh
recovered=$(mktemp -d)
tar -xJpf evidence/issue-3820/native-capacity-registry-outputs.tar.xz -C "$recovered"
```
