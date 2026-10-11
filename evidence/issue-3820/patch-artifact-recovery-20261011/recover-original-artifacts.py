import hashlib
import io
import json
import pathlib
import re
import subprocess
import zipfile

out = pathlib.Path(__file__).parent / "original-artifact-recovery"
out.mkdir(exist_ok=True)
context = pathlib.Path(
    "/Users/teacher/.codex/automations/imi-merge-verify-closer/work/20261011T0627Z/expanded-artifacts/comparison-results-38118258124/verifier-context.md"
).read_bytes()
m = re.search(rb"### Retrieval diagnostics\s*```json\s*(.*?)\s*```", context, re.S)
diagnostics = json.loads(m.group(1))
ids = list(
    dict.fromkeys(
        int(x["detail"].split()[-1]) for x in diagnostics["failures"] if x["channel"] == "artifacts"
    )
)
rows = []
used = 0
blocked = False
for artifact in ids:
    row = {
        "artifact_id": artifact,
        "source_run": 38118258124,
        "original_failure_kinds": [
            x["kind"] for x in diagnostics["failures"] if x["detail"] == f"artifact {artifact}"
        ],
        "status": "UNKNOWN",
    }
    rows.append(row)
    if blocked:
        row["reason"] = "Earlier REST capacity failure; no retry loop"
        continue
    meta = subprocess.run(
        ["gh", "api", f"repos/stranske/Workflows/actions/artifacts/{artifact}"],
        capture_output=True,
        timeout=60,
    )
    if meta.returncode:
        row["reason"] = meta.stderr.decode()[:500]
        blocked = "rate limit" in row["reason"].lower()
        continue
    (out / f"{artifact}-metadata.json").write_bytes(meta.stdout)
    d = json.loads(meta.stdout)
    row.update(
        name=d["name"],
        metadata_sha256=hashlib.sha256(meta.stdout).hexdigest(),
        workflow_run=d["workflow_run"],
    )
    if (
        d.get("expired")
        or not 0 <= d["size_in_bytes"] <= 8 * 1024 * 1024
        or used + d["size_in_bytes"] > 64 * 1024 * 1024
    ):
        row["reason"] = "Expired or explicit8MiB/archive64MiB/global bound"
        continue
    archive = subprocess.run(
        ["gh", "api", f"repos/stranske/Workflows/actions/artifacts/{artifact}/zip"],
        capture_output=True,
        timeout=90,
    )
    if archive.returncode:
        row["reason"] = archive.stderr.decode()[:500]
        blocked = "rate limit" in row["reason"].lower()
        continue
    used += len(archive.stdout)
    if len(archive.stdout) > 8 * 1024 * 1024 or used > 64 * 1024 * 1024:
        row["reason"] = "Actual compressed-byte bound exceeded"
        continue
    (out / f"{artifact}.zip").write_bytes(archive.stdout)
    row.update(
        status="raw-archive-recovered",
        archive_bytes=len(archive.stdout),
        archive_sha256=hashlib.sha256(archive.stdout).hexdigest(),
    )
    with zipfile.ZipFile(io.BytesIO(archive.stdout)) as z:
        members = z.infolist()
        row["members"] = [
            {
                "name": v.filename,
                "uncompressed_bytes": v.file_size,
                "compressed_bytes": v.compress_size,
                "crc32": v.CRC,
            }
            for v in members
        ]
        row["total_uncompressed_bytes"] = sum(v.file_size for v in members)
    row["acceptance"] = (
        "Raw original archive bytes only; no proof sufficiency/native input admission"
    )
(out / "recovery.json").write_text(
    json.dumps(
        {
            "original_context_sha256": hashlib.sha256(context).hexdigest(),
            "rows": rows,
            "archive_bytes": used,
            "acceptance": False,
        },
        indent=2,
    )
    + "\n"
)
print(
    json.dumps(
        {
            "targets": len(ids),
            "recovered": sum(x["status"] == "raw-archive-recovered" for x in rows),
            "archive_bytes": used,
            "rows": [
                {k: v for k, v in x.items() if k in ("artifact_id", "status", "reason")}
                for x in rows
            ],
        }
    )
)
