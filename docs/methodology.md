# Methodology and limits

## What this alpha measures

An exact model configuration responding to a small set of text/JSON programming microtasks. Passing means satisfying the task's explicit grader. It does not establish repository-level implementation skill, architecture judgment, security assurance, or performance inside a native agent product.

The comparison unit includes provider, requested model, returned model identity when available, native effort, output cap, task-suite content hash, repetitions and evaluation time. Equivalent setting names are not assumed to imply equivalent compute or capability.

## Recommendations

Advice is provisional and limited to the evaluated category and configuration. Each candidate must have the same completed task/repetition coverage and meet the stated quality threshold. Repeating one task does not produce more unique tasks. Synthetic demo records cannot justify a live-model recommendation.

The alpha records provider-reported usage but does not compute monetary costs; pricing metadata, when supplied, is not a billing calculation. Cost remains unknown and no savings claim is made. Future cost-based advice must identify supplied prices as estimates and account for cache pricing and failed calls. Errors and failed outputs remain part of the evaluation. No hidden retries or removal of failed attempts.

The included public microtasks are practice tests. They are not a private holdout, contamination-resistant benchmark or calibrated certification. Small observed differences are not proof of superiority. Even a perfect score is provisional evidence only. Architecture and autonomous implementation recommendations need stronger future task packs and validation.

The run format validates the full candidate/task/repetition matrix, strict metric types and internal provenance consistency. It does not authenticate who produced an imported JSON file. A suite hash identifies recorded suite content; without the original suite it cannot independently prove the task manifest or results. Do not treat an externally edited report as trusted measurement.

Below three repetitions per task, recommendations retain all candidates meeting the pilot quality threshold. At three or more repetitions, eligible candidates can be selected by the lowest observed median latency in that run. This is descriptive, not a confidence interval or evidence of statistical superiority.

## Provider controls

- [OpenAI reasoning](https://developers.openai.com/api/docs/guides/reasoning): effort is model-specific; reasoning tokens are included in output usage. Incomplete outputs can still consume tokens.
- [OpenAI/Codex model controls](https://learn.chatgpt.com/docs/models): native orchestration settings such as Ultra must not be invented as API effort values.
- [Anthropic effort](https://platform.claude.com/docs/en/build-with-claude/effort): effort and thinking mode are separate controls and support varies by model.

These references were reviewed on 2026-09-05. Consult current provider documentation before adding a configuration. The alpha does not discover account availability or certify every configured setting in advance.

## Architecture direction

The first slice uses a small standard-library runner to keep installation and offline verification simple. A provider protocol and separate grading/recommendation layers leave room for maintained evaluation backends when full agent execution is introduced. [Inspect](https://inspect.aisi.org.uk/models.html) and [Promptfoo](https://www.promptfoo.dev/docs/guides/evaluate-coding-agents/) are candidates; no dependency on either is present in this alpha.
