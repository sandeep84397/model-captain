# Security

Do not put credentials, private prompts or sensitive reports into public issues.

ModelCaptain's alpha runs text/JSON microtasks. It must never execute model-generated code, upload repositories, follow credential-bearing redirects, or send requests to arbitrary hosts. Live API access is explicit and uses environment credentials. Local reports can contain model output and should be treated as private, untrusted data.

Request counts and output caps are not hard monetary budgets. Provider billing, API limits and native model settings remain provider-specific.

For a sensitive vulnerability, use GitHub's private vulnerability reporting on this repository when available. For ordinary non-sensitive bugs, open an issue with a minimal example and redact local data.
