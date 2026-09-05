# Contributing

ModelCaptain is an early alpha. Discuss larger changes in an issue before implementing them.

## Development

Use Python 3.11 or newer and an isolated virtual environment:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell.

Write a failing behavioral test before a fix. Keep provider requests behind the transport boundary; unit tests must not make paid API calls. Tests should assert real request/response handling and user-visible results, not a model's self-reported success. Use small, independently checked fixtures.

## Pull requests

Include the problem, behavior change, tests run, and limitations. Keep API keys, local configs, reports and model outputs out of commits. Add provider integration tests using literal response fixtures; live compatibility results must identify exact model, settings and date.

## Evaluation contributions

State what a task measures and what it does not measure. Document the reference answer and why the grader is appropriate. Public practice tasks must not be described as sealed holdouts. Never submit private code or reference data without permission.
