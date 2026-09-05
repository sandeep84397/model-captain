# How ModelCaptain will choose models and effort

ModelCaptain's intended recommendation is conditional: for this task category, environment, quality requirement and budget, these measured configurations are reasonable candidates. A model name alone cannot determine the answer.

## 1. Define what success means

Describe the workload before comparing models: task category, language/framework, context size, number of affected components and consequence of failure. Define independent acceptance checks. A formatting task and an authentication change require different evidence.

In this alpha, categories are explicit. `--task` supplies task text for a prompt; it does not perform a validated automatic risk classification. Users must choose the appropriate category. Automatic task classification is future work and must be evaluated for wrong routing as well as correct routing.

## 2. Treat configurations as separate candidates

Astra with medium effort and Astra with high effort are two candidates. A model at its default setting is another explicit configuration. Keep native parameter names and capabilities: settings with the same label across providers are not assumed equivalent.

Future agent evaluations must also record system instructions, tools, context management, permissions, version and orchestration. API response tests and native-agent results belong to separate comparison tracks. Ultra-style orchestration is not a setting to invent in an API request.

## 3. Measure against controlled tasks

Give candidates equivalent tasks and resource limits. Keep reference answers out of prompts. Count all attempts, including malformed output, refusal, truncation, timeout and failed tests. Repeat trials and vary order when extending the evaluation system. Verify that the provider's returned model matches the candidate identity.

The alpha supplies public programming microtasks graded by exact answers or structured JSON. It does not execute generated code or prove that a proposed patch works. Later repository evaluation needs isolated workspaces and independent tests that the candidate cannot rewrite to pass.

## 4. Require quality before optimizing resources

Discard candidates that do not meet the chosen quality requirement or have inadequate/comparatively different task coverage. For high-consequence work, an average pass rate cannot compensate for a critical security or data-integrity failure.

The alpha uses a fixed pilot quality threshold and minimum unique-task count. This is a screening rule, not a calibrated safety guarantee. A small suite cannot establish a generally safe autonomy level. Stronger releases need risk-specific thresholds, separate validation tasks, and uncertainty estimates that account for repeated/related tasks.

## 5. Compare complete effort, not short answers

Measure provider-reported usage, successful and failed attempts, tool and retry cost, wall time, and where relevant human correction. Do not add reasoning tokens twice when already included in output usage. Do not treat unknown costs as zero. API cost estimates cannot stand in for an opaque subscription allowance.

Among configurations meeting quality, compare cost and latency tradeoffs. A user prioritizing completion speed may choose differently from one prioritizing expense. More than one candidate can be reasonable. The alpha labels observations as provisional, uses supplied pricing only as an estimate, and returns a shortlist when evidence does not support ordering.

For example (hypothetical, not a measured result): medium and high both satisfy required checks; high consumes more resources without a useful quality improvement. Medium is the economical candidate for this tested category. If high prevents an important failure that medium repeatedly makes, high can be justified. This does not automatically transfer to another category or provider.

## 6. Turn evidence into a usage policy

For each tested category, report candidate model IDs and settings, measured outcomes, task counts, scope, date and limits. Include a task prompt with context, constraints and verification requirements. Instructions describe a configuration; the user or a supported runtime must actually select it.

The current `recommend` and `export` commands read existing local evidence without making new API requests. They must not pretend a configuration was changed. Model response text cannot become executable configuration or exported agent instructions.

## 7. Validate routing on unseen work

Before describing a policy as validated, test it on tasks excluded from its design. Compare the proposed route against baselines such as a fixed default model, including classification mistakes and escalation costs. A stronger model may be appropriate immediately when risk warrants it; forcing every task through cheap-to-expensive retries can cost more overall.

This validation stage is roadmap work. The alpha does not learn, certify or automatically enforce an escalation policy.

## 8. Refresh only when needed

New models, changed pricing, changed runtime tools and changed workloads can invalidate advice. Future calibration should begin with a small candidate comparison, expand promising or uncertain cases within a user-defined budget, and revalidate before changing deployed policy. An untested model stays untested; being new does not assign it an architecture or review role.

See [methodology](methodology.md), [roadmap](roadmap.md) and [the alpha scope](superpowers/specs/2026-09-05-cli-alpha.md) for implemented boundaries and planned additions.
