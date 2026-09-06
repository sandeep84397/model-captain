# Harder programming benchmark (experimental)

`src/model_guide/data/programming-hard.json` is an opt-in, public 12-task text suite. It extends the original nine-task pilot with multi-step state traces, competing fixes and mutation-based test selection. It is **designed to be harder, not empirically calibrated**. No model results or ranking are implied by its answer-key tests.

## What it measures

| Category | Tasks | Required reasoning |
| --- | ---: | --- |
| Debugging | 4 | TTL boundaries plus LRU eviction; optimistic transaction conflicts; delivery/crash deduplication; weighted-path algorithm failure |
| Code review | 4 | Authorization predicate equivalence; tenant cache-key collisions; conditional-update interleavings; path validation order under explicit toy semantics |
| Testing | 4 | Compute mutant kill matrices and minimum test sets for interval overlap, capped backoff, keyset pagination and stable deduplication |

Every prompt states its inputs, operational semantics, output fields and ordering. Exact JSON grading scores an entire task as pass/fail. Minimum test sets use a defined lexical tie-breaker. There is no judge model, subjective rubric, network dependency or execution of model-generated code.

Reference answers are distributed publicly for audit, but only the problem prompt is sent in live runs. Trusted offline Python oracles simulate the state machines and exhaustively enumerate candidate test subsets; they never evaluate prompt strings or model output as code. Public tasks are susceptible to contamination and are not a private holdout set.

## Run from a repository checkout

After installing ModelCaptain, perform an offline plumbing check:

```sh
model-captain init
model-captain evaluate --provider demo --suite src/model_guide/data/programming-hard.json --output results/hard-demo.json
```

Demo output is synthetic and must never be interpreted as model performance.

To run one subscription configuration, put exactly one model/effort candidate in `native-config.json`, using `examples/native-config.json` as the schema reference. Then:

```sh
model-captain evaluate-native --provider codex-cli --config native-config.json --suite src/model_guide/data/programming-hard.json --output results/hard-native.json --repetitions 1 --max-requests 12 --live
model-captain report --input results/hard-native.json
```

The suite also works with the existing API evaluator's `--suite` option. The JSON is included as package data in installed wheels; checkout paths above assume a repository checkout.

## Comparison procedure

1. Freeze the suite and retain its SHA-256 hash. Do not compare scores against the original nine-task suite as if they shared difficulty.
2. Use the same suite, CLI version, available tools and host settings for every candidate. Keep API and native CLI tracks separate.
3. Start with a broad one-repetition screening run. Failures, unsupported settings, missing identity and incomplete runs remain visible. Screening is not a final ranking.
4. Re-test promising configurations on additional, independently authored tasks and repeated runs. Three repetitions are a practical starting point, not a statistical guarantee. Run order/load/caching can affect latency; alternate configuration order across separately labeled runs. Do not silently pool incomparable runs.
5. Choose configurations meeting an explicit quality requirement, then examine time and measured resource use. If all configurations saturate this suite, increase task complexity; do not manufacture a winner from tiny timing differences.

For the proposed 24-configuration native matrix, this suite plans **288 invocations per repetition, or 864 for three repetitions**. That is higher than the old nine-task suite's 216/648. Split configurations into validated files and set `--max-requests` for each file. These counts are CLI invocations; internal provider retries, token ceilings and subscription quota costs are unknown. No broad model run was performed when adding this suite.

## Limits and next step

This measures constrained text reasoning about small programs. It does not measure editing a repository, running tests, architecture decisions, long-horizon autonomous work or production security assurance. Auth and path exercises use fully specified toy policies, not general real-world security claims.

The current Codex native stream does not expose returned model identity, so automatic verified model recommendations remain blocked even if every task passes. A future programming benchmark should separately evaluate real repository fixes in a controlled tool environment, capture model/runtime identity where available and add private, independently scored tasks. No current result establishes a universal model hierarchy or equivalence between identically named effort levels across models.
