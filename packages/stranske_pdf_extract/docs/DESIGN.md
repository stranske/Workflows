# `stranske-pdf-extract` — design, distribution decision, and migration plan

Status: **proposed / scaffolded** · Owner: fleet platform · Date: 2026-06-28

Grounding docs (read these first; this design does not restate them):
- `Code/Audits/2026-06-28-fleet-pdf-extraction-survey.md` — who does PDF work, every disparate attempt.
- `Code/Audits/2026-06-28-pdf-extraction-methodology.md` — how the field does extraction; recommended stack.

This document is deliverables **2 (design)**, **3 (distribution decision)**, and **4 (migration plan)** of the
single-source PDF-extraction initiative. The library skeleton in this package is deliverable **5 (scaffold)**.

---

## 0. What we are replacing (verified by reading source, 2026-06-28)

Four repos independently reimplement the same shape — text-extraction ladder + OCR fallback + orchestration +
a result/provenance contract — with four divergent contracts and three OCR strategies:

| Repo | File | Library/ladder | OCR | Result contract | Maturity |
|------|------|----------------|-----|-----------------|----------|
| **Pension-Data** | `src/pension_data/parser/pdf_pipeline.py` + `extract/orchestration/fallback.py` + `db/models/provenance.py` | pypdf + injectable OCR + **staged fallback chain** | injectable callable (`ocr_extract`) | `PDFParserResult` + page-level evidence + `EvidenceReference`/`MetricEvidenceLink` | **Most mature contract** (page-level evidence, `method` enum, stable ids, per-link confidence) |
| **Inv-Man-Intake** | `src/inv_man_intake/extraction/providers/base.py` + `orchestrator.py` | dependency-free regex (fixture-grade, **not real**) | none (escalates) | `ExtractionProvider` Protocol + `ProviderExtractionOutput` + `SourceLocation`(**bbox**)/`SnippetMetadata` | **Most mature seam** (runtime-checkable Protocol, bbox + char-offset provenance, validators) |
| **Counter_Risk** | `src/counter_risk/parsers/daily_holdings_pdf.py` | **pdfplumber → pypdf → OCR** ladder, all import-guarded | **bundled** pytesseract + pdf2image | `dict[str,float]` (domain rows) | Best **OCR ladder** (graceful degradation per stage) |
| **Manager-Database** | `utils/extract.py` | pdfplumber only | none | raw `str` | Trivial — easiest migration |

Separate concern (PDF **generation**, out of scope): PAEM `pa_core/viz/pdf_report.py`, TPP
`approval_packet.py`/`prompt_flow.py`. **Not** part of this initiative.

The shared surface is items 1–4 (text extraction, OCR fallback, orchestration, result/provenance contract).
**Item 5, domain field-parsing, stays in each consumer** (Counter_Risk's repo-cash regex, Pension-Data's
funded/actuarial metric extraction, etc.). The library never learns a consumer's domain schema.

The single biggest gap: **none of the four has a reliability layer** (arithmetic/business-rule validation,
cross-check, calibrated confidence). The methodology doc rates this the highest-leverage and it is absent
fleet-wide. We design it in from day one.

---

## 1. The shared core — what the library owns

```text
stranske_pdf_extract/
  contract.py        # the one result + page-level-provenance contract (generalizes PD + IMI)
  provider.py        # ExtractionProvider / MultiModalExtractionProvider Protocols + registry + OCR seam
  orchestration.py   # run_fallback_chain primitive (lifted from Pension-Data, already generic)
  reliability.py     # arithmetic/business-rule validation + cross-check + calibration  (GREENFIELD)
  providers/
    docling_provider.py    # one REAL extractor behind the Protocol (Docling, MIT, local) — optional dep
    text_baseline.py       # pure-python pdfplumber/pypdf baseline so the ladder + tests run with no native deps
  eval/
    harness.py       # shared golden-set eval harness (normalize-then-compare, per-field F1) — optional deps
```

### 1.1 Contract (`contract.py`) — generalize the two mature ones, do not invent a third

The merge rule: **take IMI's modality-grouped raw output + bbox provenance** (strictly richer locator than
PD's string refs) and **take PD's evidence-ref canonicalization + `method` enum + stable ids + per-link
confidence** (richer linkage semantics). Concretely:

- `SourceLocation(doc_id, page, bbox, table_index, image_index)` — from IMI. `bbox` is the superset locator;
  PD's `p.40#table` string is derivable from it (`EvidenceRef.canonical`), so both consumers serialize losslessly.
- `SnippetMetadata(kind, char_start, char_end)` — from IMI; the replayable excerpt offsets.
- `ExtractionMethod` = `text | table | ocr | fallback | llm | vision` — from PD's `method` enum, extended for
  the methodology's vision-table path.
- `EvidenceRef` — PD's canonical string form (`doc#page=n`, `doc#anchor=…`, `p.40#table`) **plus** a stable
  `ref_id` (content hash, excludes enrichment fields exactly as PD does — enrichment never changes identity).
- `ExtractedTextBlock / ExtractedTableCell / ExtractedTable / ExtractedImage / ProviderExtractionOutput` — the
  raw modality output, from IMI. This is what a layout extractor (Docling) naturally emits.
- `ExtractedField(key, value, confidence, location, snippet, snippet_metadata, method)` — from IMI.
- `ExtractedDocumentResult(doc_id, provider_name, fields, stage_name, stage_confidence, attempts, escalation,
  escalation_required, flags, provenance_refs)` — IMI's result **fused with** PD's `PDFParserResult` outcome
  metadata (stage/attempts/escalation/flags). One result type both consumers can adopt.
- Validators (`validate_provider_output`, `validate_extracted_document_result`) — from IMI, extended with PD's
  strict-mode rule (high-impact fields must carry an evidence ref).

Why generalize rather than pick one: PD's provenance is string-ref based (loses bbox); IMI's is bbox-based but
lacks the `method` enum, stable ids, and per-link confidence PD added for citation export. Each consumer needs
the other's strengths. Generalizing once is the whole point of the initiative.

### 1.2 Provider Protocol + OCR seam (`provider.py`)

Lift IMI's two `@runtime_checkable` Protocols verbatim (they are already the right seam):
- `ExtractionProvider.extract(doc_id, content: bytes) -> ExtractedDocumentResult` (field-level).
- `MultiModalExtractionProvider.extract_modalities(doc_id, content: bytes) -> ProviderExtractionOutput` (raw).

Plus PD's OCR-as-injection idea, promoted to a named type: `OcrExtract = Callable[[bytes], Sequence[str]]`.
A repo can **bundle** Tesseract (Counter_Risk's pattern) or **inject** its own (Pension-Data's pattern) — the
library never hard-codes an OCR engine. Docling/pdfplumber/pypdf/OCR/Textract are all just providers behind
the same Protocol; a registry resolves them by name.

### 1.3 Orchestration (`orchestration.py`)

Lift Pension-Data's `run_fallback_chain[TResult]` — it is **already generic** (`ParserStage[TResult]`,
completeness predicate, `EscalationEvent`, best-partial selection, structured `ParserAttempt` records). This is
the canonical fallback ladder: try stages in order, accept first that satisfies `is_complete`, escalate with a
structured event on exhaustion, keep the best partial. IMI's `ExtractionOrchestrator` (tracing/retry/metrics)
becomes an optional richer driver layered on top, not the primitive.

### 1.4 Reliability (`reliability.py`) — greenfield, highest leverage

Per the methodology doc §5 (cheapest + most trustworthy first):
1. **Arithmetic / business-rule validation** — foot/cross-foot subtotals→totals, weights sum to 100%,
   sign/currency sanity, date-in-period. Deterministic, dependency-free. Violations localized to page+row via
   the evidence ref (arXiv 2511.10659: 84% of fiscal-doc errors localize this way). **LLM says *what*,
   deterministic code does the arithmetic** — never let the model do the sum.
2. **Cross-check** — two structurally different providers → agree=auto-accept, disagree=flag the *specific*
   field for review (label-free correctness signal).
3. **Confidence routing** — ECE measurement and the existing double-threshold router
   (`accept_at=0.95`, `reject_below=0.50`). If calibration is added later, document it as future work. LLMs
   are systematically overconfident; never route on raw confidence without measuring ECE on real data first.

### 1.5 Eval harness (`eval/harness.py`)

Golden-set runner: **normalize-then-compare** (numbers as parsed numerics, dates canonical — not raw
exact-match), per-field precision/recall/F1 **macro-averaged** (rare-but-critical fields count). Optional
DeepEval pytest gate and LangSmith dataset hooks (LangSmith is already wired in some fleet repos). Shipped in
the shared library so every consumer inherits the same scorer and CI gate.

---

## 2. Distribution decision (deliverable 3) — **installable package, not copy-sync**

**Decision: ship `stranske-pdf-extract` as an installable, semver-tagged Python package, pip/uv-installed from
git source. Home it as a subdirectory package inside the Workflows repo** (`Workflows/packages/stranske_pdf_extract/`),
installed via `pip install "git+https://github.com/stranske/Workflows@pdf-extract-vX.Y.Z#subdirectory=packages/stranske_pdf_extract"`,
released under a dedicated tag prefix `pdf-extract-v*`. Confidence: **high** for package-over-copy-sync;
**medium** for subdir-of-Workflows over a dedicated repo (see upgrade path).

### Why a package beats the Workflows `tools/*` copy-sync

The `tools/*` precedent (`.github/sync-manifest.yml`, ~231 entries, copied by `maint-68-sync-consumer-repos.yml`)
exists for **single-file Python helpers that the reusable CI workflows themselves import** (`ci_failure_triage.py`,
`coverage_guard.py`, `llm_provider.py`). This tool is a different animal on every axis:

1. **Layer.** `tools/*` are imported by *workflow YAML / CI*. This is imported by consumer *application* code
   (domain parsers). Different dependency layer → different distribution.
2. **Optional native deps.** Docling, Tesseract, pdf2image are heavy/native. A package expresses these as
   **extras** (`[docling]`, `[ocr]`, `[textract]`, `[eval]`); copy-sync copies files and cannot declare or gate
   dependencies at all. Vendored loose files would force every consumer to hand-maintain the dep set.
3. **Opt-in vs forced.** Only **4 of 13** consumer repos do extraction. Copy-sync pushes files to *all*
   consumers; `pip install` is opt-in by exactly the repos that need it.
4. **Semver / independent migration.** A package lets each consumer **pin** (`stranske-pdf-extract==0.3.1`) and
   migrate on its own cadence — the explicit requirement that *no consumer's tests break*. Copy-sync couples
   every consumer to "latest synced": a library fix forces a fleet-wide sync, and there is no pin to hold a
   consumer on a known-good version during migration.
5. **It's a package, not a script.** A multi-module tree (contract/provider/orchestration/reliability/eval)
   vendored as loose files in `tools/` is awkward and breaks `import stranske_pdf_extract`.

The pure-Python core has **no** heavy deps (the ladder degrades gracefully; Docling/OCR are extras), so
"package vs copy-sync" is not about dep weight — it is about **versioning, opt-in, and layer**. On all three,
the package wins.

### Why subdirectory-of-Workflows (and the upgrade path)

- Honors the fleet's "single source of truth = Workflows; distributed from one place" principle — no new repo to
  onboard into keepalive, lanes, branch protection, CI bootstrap.
- Real pip-installability + extras + independent semver (dedicated `pd-extract-v*` tag prefix keeps it out of
  Workflows' moving tag namespace).
- Reuses Workflows CI for the library's own tests.
- **It is NOT added to `sync-manifest.yml`** — distribution is `pip`, not copy. (The only sync-manifest touch is
  documentation: note the package exists and is pip-installed, so a future audit doesn't "fix" the absence.)

**Upgrade path to a dedicated repo** (`stranske/pdf-extract`): warranted only if the library's release cadence
diverges enough from Workflows that sharing the repo causes friction (e.g., frequent library releases vs. slow
Workflows churn, or external consumers). Until then, subdir keeps operational overhead at zero. The package is
self-contained (own `pyproject.toml`), so extraction to its own repo later is a `git filter-repo` move, not a
rewrite.

> Open operational question for the owner: confirm subdir-of-Workflows vs. a dedicated `stranske/pdf-extract`
> repo. The scaffold is written to be home-agnostic so either choice is cheap.

---

## 3. Migration plan (deliverable 4) — dependency order, tests as the gate

Phased, never big-bang. **Each repo keeps its domain parser and its existing tests; those tests are the
migration gate — green before and after, no break permitted.** A consumer adopts the library by replacing its
private *extraction + orchestration + provenance* internals with calls into `stranske_pdf_extract`, leaving its
domain field-parsing untouched.

**Phase 0 — build the library (this package).** Land contract + provider + orchestration + reliability +
Docling provider + conformance test + eval harness skeleton. Tag `pdf-extract-v0.1.0`. (Issue: *Build*.)

**Phase 1 — Pension-Data (start here — most mature contract).** PD already has the closest shape (staged
fallback, page-level evidence). Migration = prove the generalized `contract.py` is a superset of
`PDFParserResult` + `EvidenceReference`, then re-point `pdf_pipeline.py`'s stage machinery at
`orchestration.run_fallback_chain` from the library and map PD's evidence model onto `EvidenceRef`. Lowest risk,
highest validation value: if the generalized contract can carry PD's page-level evidence losslessly, the
generalization is proven. Gate: PD's existing parser + provenance tests stay green.

**Phase 2 — Inv-Man-Intake (#713 consumes this, does not re-implement).** IMI's Protocol/provenance is already
the seam we lifted; migration = re-export the library's Protocols/contract from
`inv_man_intake/extraction/providers/base.py` (or alias) and implement **#713's Docling provider as a thin
adapter over `stranske_pdf_extract.providers.docling_provider`** rather than a 5th private extractor. Gate: IMI's
extraction + orchestrator tests stay green; #713's named conformance test points at the shared provider.

**Phase 3 — Counter_Risk (fold in the OCR ladder).** Replace `_extract_text_with_pdfplumber/_with_pypdf/_with_ocr`
with the library's `text_baseline` provider + injected Tesseract OCR seam, behind `run_fallback_chain`. CR keeps
`_extract_repo_cash_values` (domain). Gate: CR's daily-holdings parser tests stay green (including the
sanitized-`.pdf`-fixture fallback path).

**Phase 4 — Manager-Database (trivial).** Replace `utils/extract.py::_extract_pdf` with a one-line call into the
library's baseline provider, returning text. Smallest change; do it last as a confidence-builder. Gate: MD's
extract tests stay green.

Reliability + eval are **available from Phase 0** but adopted opportunistically per repo (PD's funded/actuarial
footing checks are the natural first real consumer of the arithmetic validators).

---

## 4. Constraints honored

- **Local-first / confidentiality.** Docling (MIT, local) is the primary real extractor; managed APIs
  (Textract/Azure DI) are optional sanity-check fallbacks only. Proprietary manager/holdings docs never have to
  leave the building.
- **Browser demos stay fixture-backed.** Docling/OCR are heavy native deps → optional extras, never imported by
  any stlite/Pyodide path. The conformance test skips cleanly when the optional dep is absent.
- **Deterministic tests.** contract/orchestration/reliability are pure-Python and fully deterministic; the
  Docling test is a Protocol-conformance check that skips without the dep. No network, no nondeterminism in CI.
- **Reliability designed in, not bolted on.** `reliability.py` ships in Phase 0.
