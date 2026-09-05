<p align="center">
  <img src="assets/modelcaptain.png" width="200" alt="ModelCaptain captain's armband and connected team nodes">
</p>

# ModelCaptain

**Measure model configurations. Learn their strengths. Choose with evidence.**

A provider-neutral CLI for running a shared evaluation battery and producing scoped usage guidance. Like a captain selecting players for their roles, ModelCaptain aims to help you select models and native settings for particular kinds of work.

**Status: early alpha.** The foundation includes nine public programming microtasks. These are a demonstration/pilot suite, **not a calibrated universal benchmark**. No model rankings or recommended vendor hierarchy are bundled. Real-world coding, architecture and autonomous-agent capability are not established by this suite.

## Why this exists

Model names and labels such as medium, high and xhigh do not tell you enough about suitability. ModelCaptain treats each model + native setting as a candidate and keeps measured quality, usage and time visible. Start with [the measurement framework](docs/measurement-framework.md) and [how selection works](docs/selection-process.md). Project-specific calibration is optional future work; the core direction is a common, versioned test battery and multidimensional capability profiles.

## Install from source

Python 3.11 or newer. No runtime dependencies.

```sh
git clone https://github.com/sandeep84397/model-captain.git
cd model-captain
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
model-captain --help
```

On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell. Install from this repository; no PyPI publication is claimed.

## Offline demonstration

```sh
model-captain init
model-captain evaluate --provider demo --output results/demo.json
model-captain report --input results/demo.json
model-captain export --input results/demo.json --format agents-md --output results/DEMO-AGENTS.md
```

This creates local `model-guide.json` configuration and a synthetic report. **No API keys or model calls.** Default demo: 9 synthetic attempts. Demo data cannot recommend real models.

```sh
model-captain recommend --input results/demo.json --category debugging --task "Find the cause of a concurrency bug"
```

Demo recommendation intentionally returns exit code **2** with demonstration-only status. Demo export succeeds, but clearly marks its document as a demonstration rather than deployable routing advice.

## Evaluate configured API models

Replace starter `replace-me` model IDs in `model-guide.json` with exact IDs available to your account. Add separate candidates to compare native effort settings. Support varies by model; the provider remains the authority on compatibility. Ultra orchestration is not an API effort setting.

```json
{
  "version": 1,
  "candidates": [
    {"id": "openai-medium", "provider": "openai", "model": "YOUR_EXACT_OPENAI_MODEL_ID", "effort": "medium", "max_output_tokens": 4096},
    {"id": "anthropic-medium", "provider": "anthropic", "model": "YOUR_EXACT_ANTHROPIC_MODEL_ID", "effort": "medium", "max_output_tokens": 4096}
  ]
}
```

Set `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` in your environment. Never put keys in configuration or reports.

```sh
# Paid API calls require explicit opt-in.
model-captain evaluate --provider openai --live --output results/openai.json
model-captain evaluate --provider anthropic --live --output results/anthropic.json

# One comparable run: 2 candidates × 9 tasks × 3 repetitions = 54 calls.
model-captain evaluate --provider all --live --repetitions 3 --max-requests 54 --output results/comparison.json
```

`all` selects live providers, excluding demo. The entire configuration, credentials, prompt sizes and planned calls are checked before requests. Runs above the request cap are rejected, not silently truncated. Default cap: 12 requests. No hidden retries.

Request and output limits **do not guarantee a dollar budget**. A low output cap can truncate reasoning-model answers; truncation counts as failure. Only fixed official endpoints are supported. Provider contracts are tested offline; live compatibility and benchmark results require separately recorded live runs.

## Read evidence and generate guidance

```sh
model-captain report --input results/comparison.json
model-captain recommend --input results/comparison.json --category debugging --task "Diagnose a race condition; preserve the public API and add regression tests"
model-captain export --input results/comparison.json --format agents-md --output results/AGENTS.md
model-captain export --input results/comparison.json --format claude-md --output results/CLAUDE.md
```

These commands make no model calls. Advice requires comparable complete coverage and verified model identity. The pilot threshold is at least 3 distinct tasks and 0.8 quality; this is **not** a confidence or safety guarantee. Unknown cost stays unknown. A shortlist can be more appropriate than a single candidate.

Instructions do not change your app's active model or grant autonomous permissions. `--task` supplies prompt text, not a validated classifier. Model-produced text is never executed or promoted into exported instructions.

## Custom suites and limits

Use `evaluate --suite path/to/suite.json`. The bundled [`programming.json`](src/model_guide/data/programming.json) is the format reference. Graders support exact answers and JSON subset checks. Reference answers stay out of live provider prompts.

The alpha does not accept `--project`, execute generated code, upload repositories, discover account models or benchmark native Codex/Claude Code. Those concept capabilities remain [roadmap work](docs/roadmap.md).

## Development

```sh
python -m unittest discover -s tests -v
python -m model_guide --help
```

Tests use controlled transport fixtures and offline data. CI runs tests and installed CLI smoke on Python 3.11–3.14.

See [methodology](docs/methodology.md), [contributing](CONTRIBUTING.md) and [security](SECURITY.md). MIT licensed. Independent project; not affiliated with OpenAI or Anthropic. Logo concept generated with AI.
