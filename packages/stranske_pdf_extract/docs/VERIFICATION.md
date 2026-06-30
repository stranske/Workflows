# stranske-pdf-extract verification evidence

This note records the release and verification evidence for Workflows issue #2711.

## CI gate

Gate includes a required `stranske-pdf-extract package tests` job, and Selftest CI mirrors
the same package suite for repository self-checks. Both jobs run:

```bash
cd packages/stranske_pdf_extract
PYTHONPATH=src python -m pytest tests
```

The suite includes the named acceptance gate:

```bash
PYTHONPATH=src python -m pytest tests/test_docling_provider.py::test_docling_provider_conforms_to_protocol
```

## Deliberate-break proof

The conformance gate depends on `DoclingProvider.name = "docling"`. A deliberate local
mutation that changes or removes that attribute must fail
`tests/test_docling_provider.py::test_docling_provider_conforms_to_protocol` at:

```python
assert provider.name == "docling"
```

Before release, run the mutation, capture the failure, revert the mutation, and confirm
the same test passes.

## Release tag

The release tag is `pdf-extract-v0.1.0`. The install URL is:

```bash
pip install "git+https://github.com/stranske/Workflows@pdf-extract-v0.1.0#subdirectory=packages/stranske_pdf_extract"
```
