# Subscription CLI evaluation

User-approved direction: evaluate through official locally authenticated Codex and Claude Code, reusing eligible subscriptions. Never extract, copy, or persist credentials. No API-key fallback. Local use only; CI tests use doubles.

## Interface

`evaluate-native --config FILE --provider codex-cli|claude-cli --output FILE --live [--suite FILE --repetitions 1 --max-requests 12 --force]`.

Native config version 1 contains candidates with exactly `id`, `provider`, `model`, `effort` and optional `timeout_seconds` (default 120; 10..600). Model and effort are explicit. No API output-token cap is claimed for native CLIs. Native `max-requests` counts CLI invocations, not underlying provider requests or retries. No ModelCaptain retry or model fallback. Both CLIs must preserve their existing security controls.

Preflight validates every selected candidate, suite, count, executable/version and subscription login before any model invocation. Reject API-related environment overrides for selected provider; never unset a billing override silently. Refuse unknown authentication. All output reservation and interruption guarantees match the API command. Print invocation count, tested configurations, per-invocation timeout, unknown token ceiling and unknown cost.

Each task runs in a new temporary working directory outside the repository. Prompt through stdin, no shell interpolation. Only task prompt reaches the model, never reference answers. Codex uses read-only sandbox and disabled shell/apps/multi-agent/web where supported; Claude uses no built-in tools, empty MCP config, no slash commands, no Chrome and normal permission enforcement. Preserve host security hooks and managed policy. Tools/customizations may still affect the native harness; report the profile and reject observed tool calls for this text pilot. Timeouts and interruption terminate the child process group on POSIX. Sanitize errors; do not persist raw stderr, account identity or tokens.

## Evidence

Separate schema version 2, `track=native-cli`, `mode=live`, `provenance.kind=subscription-cli`. Record CLI version, subscription authentication method, a fixed invocation-profile identifier, native config and exact task/repetition matrix. Attempts record success/grade, latency, provider-reported token totals (nullable), requested model and actually observed returned model (nullable). Never substitute requested model for missing observed identity. Cost and generated-token ceiling remain null.

Native reports can show pass rates and latency without verified identity. Recommendations require exact matching observed model identity for every attempt, at least 3 unique tasks, quality >=0.8 and identical provider/version/profile. Otherwise report insufficient identity/comparability evidence. Do not rank API and native tracks together. Export must preserve run/suite references and limitations.

## Verification and rollout

1. Process/CLI adapter contracts via injected subprocess runner: safe arguments, auth rejection, strict outputs, usage, missing identity, refusal/errors, timeout/interruption.
2. Native config/report validation and full coverage; unchanged API schema and regressions.
3. CLI preflight, no-live gate, collision, failed auth and mocked end-to-end run.
4. Independent review, unit suite, clean package smoke.
5. At most 18 authorized real local Codex invocations: Terra medium/high, nine pilot tasks each, one repetition, no automatic retry. Stop on authentication/transport failure. This is a smoke/pilot, not a calibrated recommendation or statistical superiority claim.
6. Publish reviewed changes and confirm CI. Report actual subscription benchmark limitations and any unavailable provider.
