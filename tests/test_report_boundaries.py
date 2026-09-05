import copy
import unittest

from model_guide.evaluation import ValidationError, build_report, grade, validate_config, validate_report, validate_suite
from model_guide.recommendations import RecommendationError, recommend


def report(repetitions=1):
    suite = {"version": 1, "tasks": [{"id": f"t{i}", "category": "debugging", "prompt": "Find defect", "grader": "exact", "expected": i} for i in range(3)]}
    candidates = [{"id": "a", "provider": "openai", "model": "model-a"}]
    attempts = [{"candidate_id": "a", "task_id": task["id"], "category": "debugging", "repetition": rep, "success": True, "passed": True, "latency_ms": 1, "input_tokens": 1, "output_tokens": 1, "cost_usd": None, "requested_model": "model-a", "returned_model": "model-a"} for task in suite["tasks"] for rep in range(1, repetitions + 1)]
    return build_report(suite, candidates, repetitions, attempts, "live")


class ReportBoundaryTests(unittest.TestCase):
    def test_normalizes_default_cap_and_safe_model(self):
        result = validate_config({"version": 1, "candidates": [{"id": "a", "provider": "openai", "model": "model-a"}]})
        self.assertEqual(result["candidates"][0]["max_output_tokens"], 1024)
        with self.assertRaises(ValidationError): validate_config({"version": 1, "candidates": [{"id": "a", "provider": "openai", "model": "bad model"}]})

    def test_provider_efforts_and_suite_values(self):
        validate_config({"version": 1, "candidates": [{"id": "a", "provider": "openai", "model": "a", "effort": "minimal"}]})
        validate_config({"version": 1, "candidates": [{"id": "a", "provider": "anthropic", "model": "a", "effort": "max"}]})
        for provider, effort in (("anthropic", "minimal"), ("demo", "none")):
            with self.assertRaises(ValidationError): validate_config({"version": 1, "candidates": [{"id": "a", "provider": provider, "model": "a", "effort": effort}]})
        with self.assertRaises(ValidationError): validate_suite({"version": 1, "tasks": [{"id": "a", "category": "testing", "prompt": " ", "grader": "exact", "expected": 1}]})
        self.assertFalse(grade("NaN", "exact", 1))

    def test_exact_tuple_coverage_and_failure_denominator(self):
        valid = report(2); validate_report(valid)
        changed = copy.deepcopy(valid); changed["attempts"][-1]["repetition"] = 1
        with self.assertRaises(ValidationError): validate_report(changed)
        changed = report(); changed["attempts"][0]["success"] = False; changed["attempts"][0]["passed"] = False; changed["attempts"][0]["returned_model"] = None
        with self.assertRaises(RecommendationError): recommend(changed, "debugging", "fix")

    def test_top_level_tasks_and_mixed_provider_rejected(self):
        valid = report(); self.assertIn("tasks", valid); self.assertNotIn("task_manifest", valid)
        changed = copy.deepcopy(valid); changed["candidates"][0]["provider"] = "demo"
        with self.assertRaises(ValidationError): validate_report(changed)
