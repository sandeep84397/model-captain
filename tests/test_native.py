import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from model_guide.native import NativeClient, NativeError


class FakeRunner:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, argv, input_text, cwd, timeout, env):
        self.calls.append((argv, input_text, cwd, timeout, env))
        return self.results.pop(0)


class NativeClientTest(unittest.TestCase):
    def test_codex_preflight_and_result_use_subscription_contract(self):
        runner = FakeRunner([
            (0, "codex-cli 1.2.3", ""),
            (0, "--json --sandbox --disable --ephemeral --skip-git-repo-check", ""),
            (0, "", "Logged in using ChatGPT"),
            (0, "\n".join([
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": '{"answer": true}'}}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 7}}),
            ]), ""),
        ])
        client = NativeClient("codex-cli", runner=runner, environ={})
        candidate = {"model": "gpt-test", "effort": "high", "timeout_seconds": 30}
        self.assertEqual(client.preflight(candidate), {
            "cli_version": "codex-cli 1.2.3", "auth_method": "chatgpt", "profile": "native-text-v1"
        })
        result = client.evaluate(candidate, "only the task")
        self.assertEqual(result.text, '{"answer": true}')
        self.assertIsNone(result.model)
        self.assertEqual((result.input_tokens, result.output_tokens), (4, 7))
        argv, prompt, cwd, timeout, _ = runner.calls[3]
        self.assertEqual(prompt, "only the task")
        self.assertEqual(timeout, 30)
        self.assertIn("exec", argv)
        self.assertIn("--json", argv)
        self.assertIn("--ephemeral", argv)
        self.assertIn("--skip-git-repo-check", argv)
        self.assertIn("read-only", argv)
        self.assertNotIn("--ask-for-approval", argv)
        self.assertIn('approval_policy="never"', argv)
        self.assertIn('model_provider="openai"', argv)
        self.assertIn('forced_login_method="chatgpt"', argv)
        self.assertIn('features.shell_tool=false', argv)
        self.assertNotIn('tools.shell_tool=false', argv)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
        self.assertNotEqual(cwd, ".")

    def test_claude_result_observes_single_model_and_rejects_tool_event(self):
        good = json.dumps({
            "type": "result", "subtype": "success", "result": "done",
            "usage": {"input_tokens": 2, "output_tokens": 3},
            "modelUsage": {"claude-test": {"inputTokens": 2, "outputTokens": 3}},
        })
        runner = FakeRunner([(0, good, "")])
        result = NativeClient("claude-cli", runner=runner, environ={}).evaluate(
            {"model": "claude-test", "effort": "medium", "timeout_seconds": 20}, "task"
        )
        self.assertEqual(result.text, "done")
        self.assertEqual(result.model, "claude-test")
        self.assertEqual((result.input_tokens, result.output_tokens), (2, 3))
        argv, _, _, _, _ = runner.calls[0]
        self.assertIn("--tools", argv)
        self.assertIn("--verbose", argv)
        self.assertIn("--no-session-persistence", argv)
        self.assertIn("--disable-slash-commands", argv)
        self.assertNotIn("--bare", argv)

        tool = json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use"}]}})
        with self.assertRaisesRegex(NativeError, "^native tool use refused$"):
            NativeClient("claude-cli", runner=FakeRunner([(0, tool + "\n" + good, "")]), environ={}).evaluate(
                {"model": "claude-test", "timeout_seconds": 20}, "task"
            )

    def test_preflight_refuses_api_override_and_unknown_auth(self):
        with self.assertRaisesRegex(NativeError, "^API or billing override is set$"):
            NativeClient("codex-cli", runner=FakeRunner([]), environ={"OPENAI_API_KEY": "secret"}).preflight({})
        runner = FakeRunner([
            (0, "claude 1.0", ""),
            (0, "--print --output-format --verbose --tools --mcp-config --no-session-persistence --no-chrome --disable-slash-commands --strict-mcp-config --permission-mode --model --effort", ""),
            (0, '{"loggedIn":true,"authMethod":"api_key"}', ""),
        ])
        with self.assertRaisesRegex(NativeError, "^unsupported native authentication$"):
            NativeClient("claude-cli", runner=runner, environ={}).preflight({})
        oauth_runner = FakeRunner([])
        with self.assertRaisesRegex(NativeError, "^API or billing override is set$"):
            NativeClient("claude-cli", runner=oauth_runner, environ={"CLAUDE_CODE_OAUTH_TOKEN": "secret"}).preflight({})
        self.assertEqual(oauth_runner.calls, [])

    def test_claude_preflight_requires_first_party_subscription(self):
        runner = FakeRunner([
            (0, "claude 1.0", ""),
            (0, "--print --output-format --verbose --tools --mcp-config --no-session-persistence --no-chrome --disable-slash-commands --strict-mcp-config --permission-mode --model --effort", ""),
            (0, '{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty","subscriptionType":"pro"}', ""),
        ])
        metadata = NativeClient("claude-cli", runner=runner, environ={}).preflight({})
        self.assertEqual(metadata["auth_method"], "claude-subscription")
        rejected = FakeRunner([
            (0, "claude 1.0", ""),
            (0, "--print --output-format --verbose --tools --mcp-config --no-session-persistence --no-chrome --disable-slash-commands --strict-mcp-config --permission-mode --model --effort", ""),
            (0, '{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"bedrock","subscriptionType":"pro"}', ""),
        ])
        with self.assertRaisesRegex(NativeError, "^unsupported native authentication$"):
            NativeClient("claude-cli", runner=rejected, environ={}).preflight({})

    def test_claude_preflight_sanitizes_malformed_auth_json(self):
        values = ["[]", "null", '"unexpected"', '{"authMethod": []}']
        for value in values:
            with self.subTest(value=value):
                runner = FakeRunner([
                    (0, "claude 1.0", ""),
                    (0, "--print --output-format --verbose --tools --mcp-config --no-session-persistence --no-chrome --disable-slash-commands --strict-mcp-config --permission-mode --model --effort", ""),
                    (0, value, ""),
                ])
                with self.assertRaisesRegex(NativeError, "^unsupported native authentication$"):
                    NativeClient("claude-cli", runner=runner, environ={}).preflight({})

    def test_native_task_directory_inside_launch_repo_is_refused_before_runner(self):
        runner = FakeRunner([])
        unsafe = os.path.join(os.getcwd(), "native-unsafe-temp")
        with patch("model_guide.native.tempfile.mkdtemp", return_value=unsafe):
            with self.assertRaisesRegex(NativeError, "^native temporary directory is unsafe$"):
                NativeClient("codex-cli", runner=runner, environ={}).evaluate(
                    {"model": "gpt-test", "timeout_seconds": 10}, "task"
                )
        self.assertEqual(runner.calls, [])

    def test_malformed_or_failed_output_is_sanitized(self):
        bad = NativeClient("codex-cli", runner=FakeRunner([(0, "not-json", "private stderr")]), environ={})
        with self.assertRaisesRegex(NativeError, "^invalid native response$") as raised:
            bad.evaluate({"model": "m", "timeout_seconds": 10}, "task")
        self.assertNotIn("private stderr", str(raised.exception))
        failed = json.dumps({"type": "result", "subtype": "error", "result": "secret"})
        with self.assertRaisesRegex(NativeError, "^native response failed$"):
            NativeClient("claude-cli", runner=FakeRunner([(0, failed, "")]), environ={}).evaluate({"model": "m", "timeout_seconds": 10}, "task")

    def test_permission_denials_and_non_boolean_is_error_are_rejected(self):
        denied = json.dumps({
            "type": "result", "subtype": "success", "result": "answer",
            "is_error": False, "permission_denials": ["private"],
        })
        with self.assertRaisesRegex(NativeError, "^native tool use refused$"):
            NativeClient("claude-cli", runner=FakeRunner([(0, denied, "")]), environ={}).evaluate({"model": "m", "timeout_seconds": 10}, "task")
        malformed = json.dumps({"type": "result", "subtype": "success", "result": "answer", "is_error": "false"})
        with self.assertRaisesRegex(NativeError, "^invalid native response$"):
            NativeClient("claude-cli", runner=FakeRunner([(0, malformed, "")]), environ={}).evaluate({"model": "m", "timeout_seconds": 10}, "task")

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_timeout_kills_native_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_path = os.path.join(directory, "child-pid")
            marker_path = os.path.join(directory, "survived")
            code = (
                "import pathlib, subprocess, sys, time; "
                "child_code=\"import pathlib, sys, time; time.sleep(0.5); pathlib.Path(sys.argv[1]).write_text('alive'); time.sleep(30)\"; "
                "child=subprocess.Popen([sys.executable, '-c', child_code, sys.argv[2]], "
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
                "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(30)"
            )
            client = NativeClient("codex-cli", environ={})
            client.command = sys.executable
            with self.assertRaisesRegex(NativeError, "^native CLI timed out$"):
                client._run([sys.executable, "-c", code, pid_path, marker_path], timeout=0.1)
            time.sleep(0.7)
            self.assertFalse(Path(marker_path).exists())

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_cleanup_targets_group_when_leader_already_exited(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_path = os.path.join(directory, "child-pid")
            marker_path = os.path.join(directory, "survived")
            code = (
                "import pathlib, subprocess, sys; "
                "child_code=\"import pathlib, sys, time; time.sleep(0.5); pathlib.Path(sys.argv[1]).write_text('alive'); time.sleep(30)\"; "
                "child=subprocess.Popen([sys.executable, '-c', child_code, sys.argv[2]], "
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
                "pathlib.Path(sys.argv[1]).write_text(str(child.pid))"
            )
            process = subprocess.Popen([sys.executable, "-c", code, pid_path, marker_path], start_new_session=True)
            process.wait(timeout=2)
            child_pid = int(Path(pid_path).read_text())
            try:
                NativeClient._stop_process(process)
                time.sleep(0.7)
                self.assertFalse(Path(marker_path).exists())
            finally:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass



if __name__ == "__main__":
    unittest.main()
