"""Subscription-authenticated, text-only local CLI adapters.

This module deliberately does not read credential files or fall back to APIs.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time


_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
NATIVE_PROFILE = "native-text-v1"
_OVERRIDES = {
    "codex-cli": {
        "OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "OPENAI_BASE_URL",
    },
    "claude-cli": {
        "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
    },
}
_FORBIDDEN_EVENT_TYPES = {
    "tool_use", "tool_call", "function_call", "command_execution", "mcp_tool_call",
    "permission_denial", "permission_denied", "web_search", "file_change", "agent_tool",
}


class NativeError(RuntimeError):
    """A safe error that never includes CLI stderr, credentials, or prompts."""


@dataclass
class NativeResult:
    text: str
    model: str | None
    input_tokens: int | None
    output_tokens: int | None


def _safe_version(value):
    if not isinstance(value, str):
        raise NativeError("native CLI version unavailable")
    lines = [" ".join(line.split()) for line in value.splitlines() if line.strip()]
    if not lines:
        raise NativeError("native CLI version unavailable")
    result = lines[-1]
    if len(result) > 128 or any(ord(char) < 32 for char in result):
        raise NativeError("native CLI version unavailable")
    return result


def _tokens(value):
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError("invalid token count")
    return value


def _has_forbidden_event(value):
    if isinstance(value, dict):
        event_type = value.get("type")
        if event_type in _FORBIDDEN_EVENT_TYPES:
            return True
        return any(_has_forbidden_event(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_forbidden_event(item) for item in value)
    return False


class NativeClient:
    """Run one official subscription CLI in a fresh, isolated task directory."""

    def __init__(self, provider, runner=None, environ=None):
        if provider not in ("codex-cli", "claude-cli"):
            raise NativeError("unsupported native provider")
        self.provider = provider
        self.command = "codex" if provider == "codex-cli" else "claude"
        self.runner = runner
        self.environ = dict(os.environ if environ is None else environ)

    def _run(self, argv, input_text="", cwd=None, timeout=30):
        if self.runner is not None:
            response = self.runner(argv, input_text, cwd, timeout, self.environ)
            if not isinstance(response, (tuple, list)) or len(response) != 3:
                raise NativeError("native CLI failed")
            return response
        if shutil.which(self.command) is None:
            raise NativeError("native CLI is not installed")
        try:
            process = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, cwd=cwd, env=self.environ, start_new_session=(os.name == "posix"),
            )
            try:
                stdout, stderr = process.communicate(input_text, timeout=timeout)
            except BaseException as exc:
                self._stop_process(process)
                if isinstance(exc, KeyboardInterrupt):
                    raise
                if isinstance(exc, subprocess.TimeoutExpired):
                    raise NativeError("native CLI timed out") from exc
                raise NativeError("native CLI failed") from exc
            return process.returncode, stdout, stderr
        except NativeError:
            raise
        except (OSError, ValueError, UnicodeError) as exc:
            raise NativeError("native CLI failed") from exc

    @staticmethod
    def _stop_process(process):
        if os.name == "posix":
            NativeClient._signal_group(process.pid, signal.SIGTERM)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if not NativeClient._group_exists(process.pid):
                    break
                time.sleep(0.05)
            if NativeClient._group_exists(process.pid):
                NativeClient._signal_group(process.pid, signal.SIGKILL)
        else:
            try:
                process.terminate()
                process.communicate(timeout=5)
            except BaseException:
                try:
                    process.kill()
                    process.communicate()
                except BaseException:
                    pass
        try:
            process.communicate(timeout=1)
        except BaseException:
            pass

    @staticmethod
    def _signal_group(pid, signal_number):
        try:
            os.killpg(pid, signal_number)
        except (ProcessLookupError, OSError):
            pass

    @staticmethod
    def _group_exists(pid):
        try:
            os.killpg(pid, 0)
        except (ProcessLookupError, OSError):
            return False
        return True

    def _check_overrides(self):
        if any(self.environ.get(name) for name in _OVERRIDES[self.provider]):
            raise NativeError("API or billing override is set")

    def preflight(self, candidate):
        self._check_overrides()
        if self.runner is None and shutil.which(self.command) is None:
            raise NativeError("native CLI is not installed")
        code, stdout, _ = self._run([self.command, "--version"])
        if code != 0:
            raise NativeError("native CLI version unavailable")
        version = _safe_version(stdout)
        code, stdout, _ = self._run(self._help_argv())
        if code != 0 or not self._supports_required_flags(stdout):
            raise NativeError("native CLI version incompatible")
        if self.provider == "codex-cli":
            code, stdout, stderr = self._run(["codex", "login", "status"])
            if code != 0 or "logged in using chatgpt" not in (str(stdout) + "\n" + str(stderr)).casefold():
                raise NativeError("unsupported native authentication")
            method = "chatgpt"
        else:
            code, stdout, _ = self._run(["claude", "auth", "status", "--json"])
            try:
                auth = json.loads(stdout)
                if not isinstance(auth, dict):
                    raise ValueError("auth")
                accepted = auth.get("authMethod") in {"claude.ai", "oauth", "subscription"}
                subscription = auth.get("subscriptionType") in {"pro", "max", "team", "enterprise"}
                if code != 0 or auth.get("loggedIn") is not True or not accepted or auth.get("apiProvider") != "firstParty" or not subscription:
                    raise ValueError("auth")
            except (AttributeError, TypeError, ValueError, RecursionError, json.JSONDecodeError) as exc:
                raise NativeError("unsupported native authentication") from exc
            method = "claude-subscription"
        return {"cli_version": version, "auth_method": method, "profile": NATIVE_PROFILE}

    def _help_argv(self):
        return ["codex", "exec", "--help"] if self.provider == "codex-cli" else ["claude", "--help"]

    def _supports_required_flags(self, output):
        if not isinstance(output, str):
            return False
        required = (
            ("--json", "--sandbox", "--disable", "--ephemeral", "--skip-git-repo-check")
            if self.provider == "codex-cli"
            else ("--print", "--output-format", "--verbose", "--tools", "--mcp-config", "--no-session-persistence", "--no-chrome", "--disable-slash-commands", "--strict-mcp-config", "--permission-mode", "--model", "--effort")
        )
        return all(flag in output for flag in required)

    def evaluate(self, candidate, prompt):
        self._check_overrides()
        if not isinstance(prompt, str):
            raise NativeError("invalid native prompt")
        timeout = candidate.get("timeout_seconds", 120)
        if type(timeout) is not int or not 10 <= timeout <= 600:
            raise NativeError("invalid native timeout")
        model = candidate.get("model")
        if not isinstance(model, str) or not _MODEL_ID.fullmatch(model):
            raise NativeError("invalid native model")
        cwd = self._new_task_directory()
        try:
            started = time.monotonic()
            code, stdout, _ = self._run(self._argv(candidate, cwd), prompt, cwd, timeout)
            _ = time.monotonic() - started
        finally:
            shutil.rmtree(cwd, ignore_errors=True)
        if code != 0:
            raise NativeError("native CLI failed")
        try:
            return self._parse(stdout)
        except NativeError:
            raise
        except (AttributeError, TypeError, ValueError, KeyError, UnicodeError, RecursionError, OverflowError, json.JSONDecodeError) as exc:
            raise NativeError("invalid native response") from exc

    @staticmethod
    def _new_task_directory():
        cwd = Path.cwd().resolve()
        directory = tempfile.mkdtemp(prefix="model-captain-native-")
        resolved = Path(directory).resolve()
        root = NativeClient._git_root(cwd)
        if NativeClient._within(resolved, cwd) or (root is not None and NativeClient._within(resolved, root)):
            shutil.rmtree(directory, ignore_errors=True)
            raise NativeError("native temporary directory is unsafe")
        return directory

    @staticmethod
    def _git_root(cwd):
        for parent in (cwd, *cwd.parents):
            if (parent / ".git").exists():
                return parent
        return None

    @staticmethod
    def _within(path, root):
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True

    def _argv(self, candidate, cwd):
        effort = candidate.get("effort")
        if effort is not None and (not isinstance(effort, str) or not _MODEL_ID.fullmatch(effort)):
            raise NativeError("invalid native effort")
        if self.provider == "codex-cli":
            argv = [
                "codex", "exec", "--json", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
                "--disable", "apps", "--disable", "multi_agent", "-c", 'approval_policy="never"',
                "-c", 'model_provider="openai"', "-c", 'forced_login_method="chatgpt"',
                "-c", "features.shell_tool=false", "-c", 'web_search="disabled"', "-m", candidate["model"], "-C", cwd,
            ]
            if effort:
                argv.extend(["-c", f'model_reasoning_effort="{effort}"'])
            return argv + ["-"]
        argv = [
            "claude", "--print", "--output-format", "stream-json", "--verbose", "--no-session-persistence",
            "--no-chrome", "--disable-slash-commands", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--tools", "", "--permission-mode", "manual", "--model", candidate["model"],
        ]
        if effort:
            argv.extend(["--effort", effort])
        return argv

    def _parse(self, stdout):
        if not isinstance(stdout, str):
            raise ValueError("stdout")
        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        if not events or any(not isinstance(event, dict) for event in events):
            raise ValueError("events")
        if any(event.get("type") in {"error", "turn.failed"} for event in events):
            raise NativeError("native response failed")
        if any(_has_forbidden_event(event) for event in events):
            raise NativeError("native tool use refused")
        return self._parse_codex(events) if self.provider == "codex-cli" else self._parse_claude(events)

    @staticmethod
    def _parse_codex(events):
        messages, completed = [], None
        for event in events:
            if event.get("type") in {"turn.failed", "error"}:
                raise NativeError("native response failed")
            if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "agent_message":
                text = event["item"].get("text")
                if not isinstance(text, str):
                    raise ValueError("message")
                messages.append(text)
            if event.get("type") == "turn.completed":
                completed = event
        if completed is None or len(messages) != 1 or not messages[0].strip():
            raise ValueError("completion")
        usage = completed.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise ValueError("usage")
        return NativeResult(messages[0], None, _tokens((usage or {}).get("input_tokens")), _tokens((usage or {}).get("output_tokens")))

    @staticmethod
    def _parse_claude(events):
        result = [event for event in events if event.get("type") == "result"]
        if len(result) != 1:
            raise ValueError("result")
        result = result[0]
        if "is_error" in result and type(result["is_error"]) is not bool:
            raise ValueError("is_error")
        if result.get("subtype") != "success" or result.get("is_error") is True:
            raise NativeError("native response failed")
        if result.get("permission_denials"):
            raise NativeError("native tool use refused")
        text = result.get("result")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text")
        usage = result.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise ValueError("usage")
        usage = usage or {}
        models = result.get("modelUsage")
        model = None
        if models is not None:
            if not isinstance(models, dict) or len(models) != 1:
                raise ValueError("model usage")
            model, model_usage = next(iter(models.items()))
            if not isinstance(model, str) or not _MODEL_ID.fullmatch(model) or not isinstance(model_usage, dict):
                raise ValueError("model usage")
        return NativeResult(text, model, _tokens(usage.get("input_tokens", usage.get("inputTokens"))), _tokens(usage.get("output_tokens", usage.get("outputTokens"))))
