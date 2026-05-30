# Research Backplane Identity-Map Conventions

This document defines the **canonical entity ID** format and alias-handling
conventions that backplane participants emit in `run-contract/v1`
`identity_refs` and `evidence-object/v1` `entity_ref`. It is the convention that
lets the orchestrator **join entities across tools**.

> **Status: P0 landing (under human review).** Part of the `run-contract/v1`
> contract set. See [`run-contract-v1.md`](./run-contract-v1.md) for the
> envelope spec and [`research-backplane-contract.md`](./research-backplane-contract.md)
> for ownership. These are *conventions*, not central code: resolution stays in
> the authoritative repos.

## Why this is a convention, not central code

Identity is **bimodal** across the fleet (`FEASIBILITY-blueprint.md` §4.4):
three repos have production-grade resolution, three have weak/none.

- Manager-Database (3/3): canonical `manager_id` + `aliases text[]` + `cik` +
  `lei` + `registry_ids jsonb`, with live EDGAR alias resolution
  (`resolve_aliases.py:139-191`).
- Pension-Data (3/3): `build_canonical_stable_id` →
  `<entity_type>:<normalized_name>[:<keys>]` (`entities/service.py:54-67`),
  exact/normalized/fuzzy matching, explicit `merge_canonical_entities`.
- Counter_Risk (3/3): strictly-validated `canonical_key` name registry
  (`name_registry.py:69-115`), but its `canonical_key` "is not surfaced as a
  shared global ID in run outputs."
- Trend_Model (0/3): funds identified by raw CSV column labels.
- Inv-Man-Intake (1/3): `aliases_json` hard-coded `None`
  (`integration.py:252`); slug-only.
- PAEM (1/3, N/A): a Monte Carlo engine over typed config has no entities to
  resolve.

The backplane join works **only because two repos already have production
resolution** — so this contract does **not** build a new central resolver.
Instead, per the feasibility memo's risk-3 mitigation ("declare
Manager-Database/Pension-Data the identity source-of-truth on day one",
§7): Workflows owns *only* the **emission format** (the canonical-ID string
shape below) and the rule for *which repos are authoritative*. Resolution stays
in the strong repos.

## Canonical ID format

A canonical entity ID is a lowercase, colon-prefixed, deterministic string:

```
<entity_type>:<normalized_identity>
```

- `entity_type` ∈ a closed vocabulary (below), lowercase snake_case.
- `normalized_identity` is a deterministic normalization of the entity's
  identifying key(s): a registry id when one exists (preferred), else a
  normalized name. Lowercase, `[a-z0-9]`, internal separators collapsed to `_`,
  with optional dotted/colon/`-` qualifiers.

Regex (enforced by the validator and the schemas'
`identity_refs`/`entity_ref` patterns):

```
^[a-z0-9_]+:[a-z0-9][a-z0-9_.:-]*$
```

Examples:

```
manager:cik_0001067983          # registry-id-anchored (preferred)
manager:berkshire_hathaway      # name-anchored fallback
fund:lei_5493001kjtiigc8y1r12
pension:calpers
provider:bloomberg
person:warren_buffett
strategy:trend_following
```

This generalizes the two strong in-repo formats: Pension-Data's
`<entity_type>:<normalized_name>[:<keys>]` and Manager-Database's
`manager_id` + registry-id columns, lifted into one fleet-wide string.

## Entity-type vocabulary (closed)

| `entity_type` | Covers | Authoritative source-of-truth repo(s) |
| --- | --- | --- |
| `manager` | Investment managers / firms / advisers | **Manager-Database** (best-in-fleet 3/3), Pension-Data |
| `fund` | Funds / vehicles / share classes | Pension-Data, Inv-Man-Intake (once aliasing is real) |
| `pension` | Pension plans / asset owners | Pension-Data |
| `provider` | Data/clearing/service providers, counterparties, clearing houses | Counter_Risk (counterparties/clearing houses), Manager-Database |
| `person` | Named individuals (PMs, signatories) | Pension-Data, Manager-Database |
| `strategy` | Strategies / asset classes / scenarios | Inv-Man-Intake (asset-class registry, fully solved), Trend_Model (target) |

Adding a new `entity_type` is an additive v1 change (new vocabulary member) with
a changelog note in this doc; removing one is breaking (→ a `v2` of the
conventions).

## Source-of-truth rule (the discipline decision)

When two tools emit a canonical ID for the same real-world entity, the
**authoritative repo's** ID wins for the join. The authority order is declared
centrally (this doc + the registry), with the day-one decision being:

1. **`manager` / `provider` / `person`** → Manager-Database is authoritative
   (live EDGAR alias resolution, `cik`/`lei`/`registry_ids`).
2. **`pension` / `fund`** → Pension-Data is authoritative (`build_canonical_stable_id`
   + explicit merge path).
3. **`strategy`** → Inv-Man-Intake's asset-class canonical key set is
   authoritative for asset classes; Trend_Model resolves its column labels *to*
   these IDs rather than inventing new ones.

A non-authoritative tool that cannot resolve to the authoritative ID emits its
best-effort name-anchored ID **and** a `confidence < 1.0` on the related evidence
object, so the orchestrator can flag the unresolved join rather than silently
fragmenting (the exact failure mode Inv-Man-Intake has today: "Summit Arc
Advisors" vs "…LLC" fragment).

## Alias handling

- **Registry-id-anchored IDs are preferred and stable** across alias variants:
  `manager:cik_0001067983` is the same entity regardless of the display name
  used in a given document.
- **Name-anchored IDs are a deterministic fallback** only. A tool that later
  resolves a name to a registry id SHOULD prefer the registry-anchored ID and
  record the prior name-anchored ID as an alias.
- **Aliases are never inlined as identity.** A run that sees "Summit Arc
  Advisors LLC" emits the canonical ID for the resolved entity (or the
  name-anchored fallback) and may carry the surface string under a
  `data_quality`/evidence note — it does not mint a second entity.
- **Merges are explicit.** When two canonical IDs are later determined to be the
  same entity, the authoritative repo records the merge (Pension-Data's
  `merge_canonical_entities`, Manager-Database's alias append) and the merged-away
  ID resolves forward. Backplane consumers treat a forwarded ID as equal to its
  target.

## What participants emit

- In `run-contract/v1` `identity_refs`: the canonical IDs of entities the run
  consumed and/or emitted (so the orchestrator can thread joins between steps).
- In `evidence-object/v1` `entity_ref` (optional): the canonical ID the
  attributed fact is about.
- Computational tools with no entities (PAEM) omit `identity_refs` entirely and
  do not list `identity` in their registry `required_sections` — they are never
  failed for it.

## What is NOT standardized

- The **resolution algorithm** stays in each authoritative repo (fuzzy/exact/EDGAR).
  Workflows does not host a resolver.
- A **global entity service / shared database** is explicitly out of scope for
  the prototype (`FEASIBILITY-blueprint.md` §2 "Depends on data & discipline":
  the join is a discipline decision, not a new service). The convention + the
  source-of-truth rule are sufficient for the 3-tool prototype.
