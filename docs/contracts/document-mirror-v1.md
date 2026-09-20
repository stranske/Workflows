# Research Backplane Document Mirror Catalog Contract

`document-mirror/v1` is the shared Workflows-owned catalog for **offline document
blobs** mirrored from upstream systems (Backstop, SharePoint, local ingest, etc.).
It is the cross-system substrate that lets triple-link HTML resolvers and
`doc-mirror` tooling validate a mirror tree without importing domain ingest code.

> **Status: proposed contract PR.** Schema:
> [`document-mirror-v1.schema.json`](./schemas/document-mirror-v1.schema.json).
> Program context: [`research-backplane-contract.md`](https://github.com/stranske/Workflows/blob/main/docs/contracts/research-backplane-contract.md) (Workflows-only; deliberately not synced to consumers).
> Related provenance: [`tracked-variable-v1.md`](./tracked-variable-v1.md) (`provenance.mirror` anchors).

## Design Decision

R4 document-access requires a fleet manifest that joins **content-addressed
blobs** under a single `mirror_root` to canonical upstream identities and
source-system URLs. Pension-Data implements checksum supersession internally
(`artifact:<sha256>` IDs); this contract exposes the mirror catalog shape so
validators, HTML resolvers, and the future `doc-mirror` CLI can share one schema.

- Every catalog **must** declare `mirror_root` and a `blobs` array (which may be
  empty after `doc-mirror init`).
- Every blob **must** carry `content_sha256`, `blob_path`, `doc_type_id`, and
  `source_refs` (the array itself is required; it may be empty for purely local
  documents with no upstream URL).
- `source_refs[]` entries are either canonical ID strings (see
  [`identity-map-conventions.md`](./identity-map-conventions.md)) or source-system
  objects for triple-link resolvers:
  - **Backstop:** `{ "system": "backstop", "url": "<https://…>" }`
  - **SharePoint:** `{ "system": "sharepoint", "driveId": "…", "itemId": "…", "web_url": "<https://…>" }`
- `blob_path` is relative to `mirror_root` using POSIX `/` separators. Absolute
  paths, `..` traversal, Windows drive prefixes (`C:`), UNC prefixes (`//` or
  `\\`), and backslashes are rejected.
- Optional `supersedes_content_sha256` records checksum supersession without
  requiring consumers to import Pension-Data ingest helpers.

## Required Fields

| Field | Requirement |
| --- | --- |
| `schema_version` | Must be the literal `document-mirror/v1`. |
| `mirror_root` | Root directory of the mirrored blob store. |
| `blobs` | Array of blob records (may be `[]` for an initialized empty catalog). |
| `blobs[].content_sha256` | Lowercase 64-hex SHA-256 of the blob bytes. |
| `blobs[].blob_path` | Mirror-relative POSIX path (no `..`, absolute paths, drive/UNC prefixes, or backslashes). |
| `blobs[].doc_type_id` | Fleet vocabulary token for the document type. |
| `blobs[].source_refs` | Array of canonical refs and/or source-system objects; may be `[]` for local-only blobs. |

## Validation

Offline validation in a consumer checkout, using its own manifest:

```bash
python -m pip install jsonschema rfc3339-validator rfc3986-validator
python scripts/validate_run_contract.py \
  --mirror-manifest path/to/your-manifest.json \
  --schema-dir docs/contracts/schemas
```

The canonical fixture and contract tests live in the
[Workflows source repository](https://github.com/stranske/Workflows), not in
consumer checkouts. From a Workflows checkout, run:

```bash
python -m pytest tests/contracts/test_backplane_schemas.py::test_document_mirror_fixture_validates -q
```
