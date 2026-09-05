# A standard measurement instrument for model capability

## Product direction

ModelCaptain begins with a shared, versioned evaluation battery. Users connect supported models and run common tasks to obtain strengths, weaknesses and resource tradeoffs. A project-specific calibration suite is optional later. Models should not be assigned roles simply from vendor descriptions or names.

The weighing-machine analogy motivates standardized conditions, reference checks and calibration. Unlike mass, language-model capability is multidimensional and task-dependent. One task or aggregate number cannot establish universal competence. Publish capability profiles and the conditions under which they were measured.

## Proposed dimensions

| Dimension | Evidence to collect | In the current alpha? |
|---|---|---|
| Reasoning | Correct answers across calibrated difficulty levels | Only tiny programming reasoning probes |
| Instruction adherence | Explicit constraints and structured-output compliance | Limited exact/JSON grading |
| Debugging | Correct diagnoses and independently verified repairs | Diagnosis microtasks only |
| Code correctness | Hidden functional and regression tests on submitted solutions | No generated-code execution yet |
| Context handling | Correct use of supplied evidence at varied context sizes | Not measured |
| Tool use | Correct actions and recovery in a controlled environment | Not measured |
| Reliability | Repeated outcomes, perturbation robustness, failure severity | Attempts recorded; no calibrated reliability estimate |
| Efficiency | Quality alongside complete cost and elapsed time | API timing/usage; incomplete cost estimates disclosed |

Missing capabilities are labeled unmeasured, not assigned a zero. Text-only and multimodal models require appropriate capability tracks. Native-agent tools and raw API configurations must have separate provenance.

## Calibration before authority

1. Select or author tasks with independently established answers and explicit coverage.
2. Run reference models to inspect task difficulty, ceiling/floor effects and discrimination.
3. Audit ambiguous/incorrect tasks and grader failures. A test that fails because of formatting should be labeled accordingly, not interpreted as a pure reasoning failure.
4. Keep development tasks separate from fresh validation tasks. Public fixed tasks can enter training data; refresh and track versions rather than claiming contamination-proof results.
5. Repeat and randomize trials, record uncertainty, and account for related questions and repeated attempts.
6. Validate that inferred strengths predict performance on unseen real tasks before generating strong use-case recommendations.

## Model and effort sweeps

Evaluate each supported native setting as a distinct configuration. Within a category, compare observed quality at different costs and latencies. Show alternatives meeting the user's quality/risk requirements. A higher effort is useful when it adds a meaningful, repeatable quality benefit; an expensive label alone is not evidence.

Keep cost and time separate. Tokens are diagnostics rather than a universal currency across tokenizers and providers. Report errors, failed attempts, missing usage and supplied-price assumptions. Cap evaluation work and distinguish screening from a validated profile.

## Efficient testing after calibration

Initially run a shared fixed battery for interpretability. Later, consider adaptive selection from a calibrated item bank, using common anchor tasks and validating that shorter evaluations retain comparability. This requires data and assumption checks; it is not equivalent to asking any model a few arbitrary difficult questions.

## From measurement to recommendations

The intended output is a dated model/configuration profile, with observed strengths, weaknesses, unmeasured dimensions, resource tradeoffs and evidence-backed use cases. The mapping from profile to roles must itself be evaluated on held-out workloads. A microtask pass cannot independently justify assigning security architecture or autonomous release responsibilities.

The alpha is infrastructure and a demonstration battery. Its nine public microtasks are not a calibrated measurement standard. It must remain explicit about this limitation in reports, exports and README.

## Research foundation

- [HELM Lite](https://crfm.stanford.edu/2023/12/19/helm-lite.html): representative scenarios, multiple measurements and limits on interpreting aggregate rankings.
- [Reliable and Efficient Amortized Model-Based Evaluation](https://crfm.stanford.edu/2025/06/04/reliable-and-efficient-evaluation.html): calibrating task difficulty and adaptive testing using Item Response Theory, integrated with HELM.
- [LiveBench](https://arxiv.org/abs/2406.19314): varied tasks with objective answers and refreshed questions to limit contamination.

These are methodological references, not dependencies, endorsements, or evidence that ModelCaptain's own suite is already calibrated.
