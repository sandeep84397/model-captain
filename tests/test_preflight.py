import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from model_guide.cli import main, bundled_suite


class PreflightTests(unittest.TestCase):
    def run_case(self, tmp, extra=(), transport=None):
        config = Path(tmp, "config.json")
        config.write_text(json.dumps({"version": 1, "candidates": [
            {"id": "one", "provider": "openai", "model": "example", "effort": "high", "max_output_tokens": 64}]}))
        argv = ["evaluate", "--config", str(config), "--provider", "openai", "--live",
                "--output", str(Path(tmp, "run.json")), *extra]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch("model_guide.cli.StdlibTransport", return_value=transport):
            return main(argv)

    def test_collision_has_zero_requests(self):
        class NoCalls:
            def post(self, *args): raise AssertionError("request before output preflight")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp, "run.json"); target.write_text("original")
            self.assertEqual(self.run_case(tmp, transport=NoCalls()), 2)
            self.assertEqual(target.read_text(), "original")

    def test_plan_printed_before_request_and_interrupt_leaves_no_report(self):
        output = io.StringIO()
        class Interrupt:
            def post(inner, *args):
                text = output.getvalue()
                for part in ("one", "example", "high", "9", "576", "cost unknown"):
                    self.assertIn(part, text)
                raise KeyboardInterrupt
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(output):
            self.assertEqual(self.run_case(tmp, transport=Interrupt()), 2)
            self.assertFalse(Path(tmp, "run.json").exists())

    def test_invalid_cap_has_zero_requests(self):
        class NoCalls:
            def post(self, *args): raise AssertionError("request with invalid cap")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.run_case(tmp, ("--max-requests", "0"), NoCalls()), 2)

    def test_force_interruption_preserves_previous_report(self):
        class Interrupt:
            def post(self, *args): raise KeyboardInterrupt
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp, "run.json"); target.write_text("original")
            self.assertEqual(self.run_case(tmp, ("--force",), Interrupt()), 2)
            self.assertEqual(target.read_text(), "original")

    def test_non_directory_output_parent_has_zero_requests(self):
        class NoCalls:
            def post(self, *args): raise AssertionError("request before output validation")
        with tempfile.TemporaryDirectory() as tmp:
            blocked = Path(tmp, "blocked"); blocked.write_text("file")
            self.assertEqual(self.run_case(tmp, ("--output", str(blocked / "run.json")), NoCalls()), 2)

    def test_all_credentials_checked_before_any_request(self):
        class NoCalls:
            def post(self, *args): raise AssertionError("request before all credentials checked")
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp, "config.json")
            config.write_text(json.dumps({"version": 1, "candidates": [
                {"id": "one", "provider": "openai", "model": "example"},
                {"id": "two", "provider": "anthropic", "model": "example"}]}))
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True), patch("model_guide.cli.StdlibTransport", return_value=NoCalls()):
                result = main(["evaluate", "--config", str(config), "--provider", "all", "--live",
                               "--max-requests", "18", "--output", str(Path(tmp, "run.json"))])
            self.assertEqual(result, 2)
            self.assertFalse(Path(tmp, "run.json").exists())

    def test_mocked_live_end_to_end_report_recommend_export(self):
        answers = {t["prompt"]: json.dumps(t["expected"]) for t in bundled_suite()["tasks"]}
        class FixtureTransport:
            def post(self, url, headers, body, timeout):
                return 200, {}, {"model": "example", "status": "completed", "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": answers[body["input"]]}]}],
                    "usage": {"input_tokens": 20, "output_tokens": 10}}
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.run_case(tmp, transport=FixtureTransport()), 0)
            report = str(Path(tmp, "run.json"))
            self.assertEqual(main(["report", "--input", report]), 0)
            self.assertEqual(main(["recommend", "--input", report, "--category", "debugging", "--task", "fix"]), 0)
            exported = Path(tmp, "guidance.md")
            self.assertEqual(main(["export", "--input", report, "--format", "agents-md", "--output", str(exported)]), 0)
            self.assertIn('"model": "example"', exported.read_text())
            self.assertIn("debugging", exported.read_text())
            run = json.loads(Path(report).read_text())
            self.assertIn(run["run_id"], exported.read_text())
            self.assertIn(run["suite_hash"], exported.read_text())
            self.assertIn("3 unique tasks", exported.read_text())
            self.assertIn("3 attempts", exported.read_text())
