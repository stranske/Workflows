# stranske-pdf-extract

Single-source PDF text-extraction for the `stranske/*` fleet — replacing four
independent, diverging implementations (Counter_Risk, Pension-Data, Inv-Man-Intake,
Manager-Database) with one installable library.

> **Design, distribution decision, and migration plan: [`docs/DESIGN.md`](docs/DESIGN.md).**
> Release and CI evidence: [`docs/VERIFICATION.md`](docs/VERIFICATION.md).
> Grounding audits: `Code/Audits/2026-06-28-fleet-pdf-extraction-survey.md` and
> `…-methodology.md`.

## What it owns (and what it does not)

Owns the shared surface: the **text-extraction ladder** (pdfplumber → pypdf → OCR, with
Docling as the real local extractor), a **page-level-provenance result contract**, a
**fallback-orchestration primitive**, and a **reliability layer** (arithmetic/business-rule
validation + cross-check + calibrated confidence routing).

Does **not** own domain field-parsing — that stays in each consumer (repo-cash regex,
funded/actuarial metrics, …). The library never learns a consumer's schema.

## Modules

| Module | Role | Provenance |
|--------|------|-----------|
| `contract` | the one result + page-level-provenance contract | generalizes Pension-Data + Inv-Man-Intake |
| `provider` | `ExtractionProvider` / `MultiModalExtractionProvider` Protocols, OCR seam, registry | Inv-Man-Intake + Pension-Data |
| `orchestration` | `run_fallback_chain` ladder primitive | Pension-Data (already generic) |
| `reliability` | foot/cross-foot, weights, dates, cross-check, ECE, confidence routing | **greenfield** (absent fleet-wide) |
| `providers.docling_provider` | real local extractor behind the Protocol (optional `[docling]`) | new — IMI #713 consumes this |
| `providers.text_baseline` | pure-python ladder; runs with no native deps | Counter_Risk ladder, generalized |
| `eval.harness` | golden-set scorer: normalize-then-compare, macro-F1, regression gate | methodology §6 |

## Install

```bash
# core (pure-python, no native deps)
pip install "git+https://github.com/stranske/Workflows@pdf-extract-v0.1.0#subdirectory=packages/stranske_pdf_extract"
# with the real local extractor / OCR / eval gate
pip install "stranske-pdf-extract[docling,ocr,eval]"   # extras: baseline, docling, ocr, textract, schema, eval
```

Distribution is **pip**, not Workflows copy-sync — see `docs/DESIGN.md` §2 for the call.

## Test

```bash
cd packages/stranske_pdf_extract
PYTHONPATH=src python -m pytest        # core suite is deterministic and dep-free
```

The Docling conformance test (`tests/test_docling_provider.py::test_docling_provider_conforms_to_protocol`)
passes with or without the `[docling]` extra; when absent, `extract_modalities()` raises
`DoclingUnavailableError`, and the test skips only if Docling is already installed.
