# Recovering the historical outputs

The [offline output archive](expanded-comparison-outputs.tar.gz) contains 20 original text and JUnit files. Recover them at their original relative paths and modes from the repository root. The [verification manifest](expanded-comparison-verification.json) retains the recorded digests.

```sh
recovered=$(mktemp -d)
tar -xpzf evidence/issue-3820/expanded-comparison-outputs.tar.gz -C "$recovered"
python - "$recovered" <<'PYTHON'
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

manifest = Path('evidence/issue-3820/expanded-comparison-verification.json')
expected = {
    name: digest for name, digest in json.loads(manifest.read_text())['sha256'].items()
    if re.fullmatch(r'evidence/issue-3820/expanded-comparison-[^/]+\.(txt|xml)', name)
}
assert len(expected) == 20, 'Expected 20 historical outputs in the manifest'
for name, digest in expected.items():
    path = Path(sys.argv[1]) / name
    assert sha256(path.read_bytes()).hexdigest() == digest, f'Checksum mismatch: {name}'
    assert path.stat().st_mode & 0o777 == 0o644, f'Mode mismatch: {name}'
print('Verified 20 historical outputs')
PYTHON
```

The [original report edition](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-all-arms-repair.md) and the [checked-in report](expanded-comparison-all-arms-repair.md) both match the manifest's report hash.

Open individual outputs at the original revision:

- [actionlint.txt](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-actionlint.txt)
- [black-final.txt](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-black-final.txt)
- [black.txt](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-black.txt)
- [diff-check.txt](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-diff-check.txt)
- [green.txt](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-green.txt)
- [green.xml](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-green.xml)
- [mutation-red.txt](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-mutation-red.txt)
- [mutation-red.xml](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-mutation-red.xml)
- [original-red.txt](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-original-red.txt)
- [original-red.xml](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-original-red.xml)
- [regression-final.txt](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-regression-final.txt)
- [regression-final.xml](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-regression-final.xml)
- [regression.txt](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-regression.txt)
- [regression.xml](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-regression.xml)
- [restored-green.txt](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-restored-green.txt)
- [restored-green.xml](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-restored-green.xml)
- [ruff-final.txt](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-ruff-final.txt)
- [ruff-verified.txt](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-ruff-verified.txt)
- [ruff.txt](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-ruff.txt)
- [template-drift.txt](https://github.com/stranske/Workflows/blob/ae4f0c8ac4ddbfd89b55112773d2917a1d4be5d6/evidence/issue-3820/expanded-comparison-template-drift.txt)
