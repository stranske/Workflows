# Target Work Environment

Read this before proposing a delivery shape for a fleet consumer. These constraints describe the confirmed target work environment; they are not a general assessment of what the repositories can run in CI or in a developer environment.

## Confirmed

- Local Python is available through a non-`PATH`, application-bundled interpreter. Do not assume that the operating system's `python` command resolves to it.
- Excel macros and Word automation work through Office COM. Direct `.docx` generation is also proven.
- Static HTML/CSS/JavaScript opened as a local file works, including deep links from the page to specific local source-document pages.

## Unverified

- WebAssembly, including Pyodide or stlite delivery, is unverified. Ordinary browser JavaScript working locally is not evidence that a `.wasm` payload works in the target environment.
- Conventional installers and administrator-dependent setup are unverified. Do not make them a prerequisite without a documented live test.

## Blocked Without Redesign

The authoritative environment response records the current hosting boundary:

> There is no server-hosted, database-backed application running anywhere I've seen.

Treat internal web services, hosted application servers, and database-backed services as blocked delivery shapes until the hosting gap is explicitly resolved. Prefer local scripts, Office artifacts, or self-contained static HTML when those forms satisfy the product need.

Source: [`stranske/Ready` work-environment response, sections A, E, and F](https://github.com/stranske/Ready/blob/main/research-program/artifacts/work-bundle/INFORMATION-REQUEST-RESPONSE.md).
