# Changelog

## 0.2.0a1

- Local subscription evaluation through official Codex and Claude Code CLIs.
- Separate native report schema, CLI version/auth/profile metadata and explicit unknown model identity.
- Native config validation, invocation limits, timeout/failure handling and no API fallback.
- Shared report/recommend/export commands preserve track and evidence provenance.
- Text-only pilot; no assertion of API/native equivalence, hard token ceilings or dollar costs.

## 0.1.0a1

Initial public alpha.

- Installable `model-captain` CLI: init, evaluate, report, recommend, export.
- Offline synthetic demonstration and opt-in OpenAI/Anthropic API adapters.
- Nine public programming microtasks covering debugging, code review and testing.
- Versioned configurations, task manifests, exact attempt coverage and provider identity checks.
- Request/output preflight, interruption handling, sanitized provider failures and unknown-cost reporting.
- Provisional category guidance and AGENTS.md/CLAUDE.md exports from validated evidence.

Limitations: no live model results bundled; no calibrated universal score, monetary cost calculation, native coding-agent harness, generated-code execution or automatic model switching. See [methodology](docs/methodology.md).
