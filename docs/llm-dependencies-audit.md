# LLM Dependencies Audit

Last audited: February 7, 2026

Scope: .github/workflows/agents-auto-pilot.yml, .github/workflows/reusable-agents-verifier.yml, .github/workflows/agents-verify-to-new-pr.yml

Findings (langchain-related packages only):

Workflow: `.github/workflows/agents-auto-pilot.yml`
Lines: 190-197
Packages: langchain, langchain-core, langchain-openai, langchain-anthropic, langchain-community

Workflow: `.github/workflows/reusable-agents-verifier.yml`
Lines: 371-374, 525-528
Packages: langchain-openai, langchain-anthropic

Workflow: `.github/workflows/agents-verify-to-new-pr.yml`
Lines: 98-101
Packages: langchain, langchain-openai, langchain-anthropic
