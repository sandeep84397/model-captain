import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from model_guide.evaluation import ValidationError
from model_guide.recommendations import RecommendationError
from model_guide.native_evaluation import (validate_native_config, validate_native_report,
    build_native_report, recommend_native)


def fixture(identity=True, repetitions=1):
    suite = {"version": 1, "tasks": [{"id": f"t{i}", "category": "debugging", "prompt": "Find result.",
        "grader": "exact", "expected": i} for i in range(3)]}
    candidates = validate_native_config({"version": 1, "candidates": [
        {"id": "medium", "provider": "codex-cli", "model": "example", "effort": "medium"}]})["candidates"]
    runtime = {"medium": {"cli_version": "1.2.3", "auth_method": "chatgpt", "profile": "native-text-v1"}}
    attempts = [{"candidate_id": "medium", "task_id": task["id"], "category": "debugging",
        "repetition": rep, "success": True, "passed": True, "latency_ms": 10,
        "input_tokens": 10, "output_tokens": 5, "cost_usd": None, "requested_model": "example",
        "returned_model": "example" if identity else None}
        for task in suite["tasks"] for rep in range(1, repetitions + 1)]
    return build_native_report(suite, candidates, repetitions, runtime, attempts)


class NativeEvaluationTests(unittest.TestCase):
    def test_unknown_profile_rejected_by_validation_recommendation_and_export(self):
        from model_guide.cli import main
        report = fixture()
        report["runtime"]["medium"]["profile"] = "unknown-harness"
        with self.assertRaises(ValidationError):
            validate_native_report(report)
        with self.assertRaises(RecommendationError):
            recommend_native(report, "debugging", "fix")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp, "run.json")
            source.write_text(json.dumps(report))
            output = Path(tmp, "AGENTS.md")
            self.assertEqual(main(["export", "--input", str(source), "--format", "agents-md", "--output", str(output)]), 2)
            self.assertFalse(output.exists())

    def test_failure_saves_incomplete_and_interrupt_leaves_no_report(self):
        from model_guide.cli import main
        from model_guide.native import NativeError
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp, "config.json")
            config.write_text(json.dumps({"version": 1, "candidates": fixture()["candidates"]}))
            output = Path(tmp, "run.json")
            args = ["evaluate-native", "--config", str(config), "--provider", "codex-cli", "--live", "--output", str(output)]
            with patch("model_guide.native_evaluation.NativeClient") as client:
                client.return_value.preflight.return_value = fixture()["runtime"]["medium"]
                client.return_value.evaluate.side_effect = NativeError("native CLI failed")
                self.assertEqual(main(args), 2)
                report = json.loads(output.read_text())
                self.assertEqual(report["completion_status"], "incomplete")
                self.assertEqual(len(report["attempts"]), 1)
                self.assertFalse(report["attempts"][0]["success"])
                self.assertEqual(client.return_value.evaluate.call_count, 1)
                output.unlink()
                client.return_value.evaluate.side_effect = KeyboardInterrupt
                self.assertEqual(main(args), 2)
                self.assertFalse(output.exists())

    def test_failed_second_preflight_prevents_all_model_calls(self):
        from model_guide.cli import main
        from model_guide.native import NativeError
        with tempfile.TemporaryDirectory() as tmp:
            candidates = fixture()["candidates"]
            candidates.append({**candidates[0], "id": "second"})
            config = Path(tmp, "config.json"); config.write_text(json.dumps({"version": 1, "candidates": candidates}))
            output = Path(tmp, "run.json")
            with patch("model_guide.native_evaluation.NativeClient") as client:
                client.return_value.preflight.side_effect = [fixture()["runtime"]["medium"], NativeError("unsupported native authentication")]
                self.assertEqual(main(["evaluate-native", "--config", str(config), "--provider", "codex-cli", "--live",
                    "--max-requests", "18", "--output", str(output)]), 2)
                client.return_value.evaluate.assert_not_called()
                self.assertFalse(output.exists())

    def test_config_closed_and_native_limits_honest(self):
        candidate = {"id": "a", "provider": "codex-cli", "model": "example", "effort": "medium"}
        normalized = validate_native_config({"version": 1, "candidates": [candidate]})
        self.assertEqual(normalized["candidates"][0]["timeout_seconds"], 120)
        self.assertNotIn("timeout_seconds", candidate)
        for extra in ({"api_key": "secret"}, {"max_output_tokens": 10}, {"effort": "ultra"}, {"timeout_seconds": True}):
            with self.assertRaises(ValidationError):
                validate_native_config({"version": 1, "candidates": [{**candidate, **extra}]})

    def test_unknown_identity_can_report_but_not_recommend(self):
        report = fixture(False)
        self.assertEqual(validate_native_report(report)["schema_version"], 2)
        self.assertIsNone(report["generated_token_ceiling"])
        with self.assertRaisesRegex(RecommendationError, "identity"):
            recommend_native(report, "debugging", "fix")

    def test_exact_matrix_and_provenance(self):
        report = fixture(repetitions=2)
        for mutation in ("duplicate", "missing", "mode", "runtime"):
            changed = copy.deepcopy(report)
            if mutation == "duplicate": changed["attempts"][-1] = changed["attempts"][0]
            if mutation == "missing": changed["attempts"].pop()
            if mutation == "mode": changed["mode"] = "synthetic"
            if mutation == "runtime": changed["runtime"]["medium"]["auth_method"] = "api-key"
            with self.assertRaises(ValidationError): validate_native_report(changed)

    def test_verified_identity_advice_stays_in_native_track(self):
        advice = recommend_native(fixture(), "debugging", "fix")
        self.assertEqual(advice["shortlist"], ["medium"])
        self.assertEqual(advice["provenance"]["track"], "native-cli")

    def test_no_live_no_invocations_and_mocked_pipeline(self):
        from model_guide.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp, "config.json")
            config.write_text(json.dumps({"version": 1, "candidates": fixture()["candidates"]}))
            output = Path(tmp, "run.json")
            args = ["evaluate-native", "--config", str(config), "--provider", "codex-cli", "--output", str(output)]
            with patch("model_guide.native_evaluation.NativeClient") as client:
                self.assertEqual(main(args), 2)
                client.assert_not_called()
                client.return_value.preflight.return_value = fixture()["runtime"]["medium"]
                client.return_value.evaluate.return_value = MagicMock(text='{}', model=None, input_tokens=10, output_tokens=3)
                self.assertEqual(main(args + ["--live"]), 0)
                self.assertEqual(client.return_value.evaluate.call_count, 9)
                self.assertEqual(main(["report", "--input", str(output)]), 0)
                self.assertEqual(main(["recommend", "--input", str(output), "--category", "debugging", "--task", "fix"]), 2)
                count = client.return_value.evaluate.call_count
                self.assertEqual(main(args + ["--live"]), 2)
                self.assertEqual(client.return_value.evaluate.call_count, count)
