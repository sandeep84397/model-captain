import copy
import unittest

from model_guide.evaluation import ValidationError, validate_config
from model_guide.evaluation import build_report, validate_report, validate_suite, grade
from model_guide.recommendations import recommend, RecommendationError


def fixture(repetitions=1):
    suite = {"version": 1, "tasks": [{"id": f"t{i}", "category": "debugging",
        "prompt": "Compute the result.", "grader": "exact", "expected": i} for i in range(5)]}
    candidates = [{"id": name, "provider": "openai", "model": name,
                   "max_output_tokens": 64} for name in ("model-a", "model-b")]
    attempts = [{"candidate_id": c["id"], "task_id": t["id"], "category": t["category"],
        "repetition": rep, "success": True, "passed": c["id"] == "model-a" or t["id"] != "t0",
        "latency_ms": 20 if c["id"] == "model-a" else 10,
        "input_tokens": 10, "output_tokens": 5, "cost_usd": None,
        "requested_model": c["model"], "returned_model": c["model"]}
        for c in candidates for t in suite["tasks"] for rep in range(1, repetitions + 1)]
    return build_report(suite, candidates, repetitions, attempts, "live")


class IntegrityTests(unittest.TestCase):
    def test_candidate_rejects_secret_fields(self):
        config = {"version": 1, "candidates": [{"id": "example",
            "provider": "openai", "model": "example", "api_key": "secret"}]}
        with self.assertRaises(ValidationError):
            validate_config(config)

    def test_config_and_suite_closed_strict_types(self):
        for version in (True, 2, "1"):
            with self.assertRaises(ValidationError):
                validate_config({"version": version, "candidates": [{"id": "a", "provider": "demo", "model": "demo"}]})
        for value in ("ultra", {}, 3):
            with self.assertRaises(ValidationError):
                validate_config({"version": 1, "candidates": [{"id": "a", "provider": "openai", "model": "a", "effort": value}]})
        with self.assertRaises(ValidationError):
            validate_suite({"version": 1, "tasks": [{"id": "a", "category": "unknown", "prompt": "x", "grader": "exact", "expected": 1}]})
        self.assertFalse(grade('{"a":true}', "exact", {"a": 1}))
        self.assertFalse(grade('NaN', "exact", float("nan")))

    def test_report_matrix_and_metrics(self):
        valid = fixture(2)
        validate_report(valid)
        mutations = []
        r = copy.deepcopy(valid); r["attempts"][-1] = r["attempts"][0]; mutations.append(r)
        r = copy.deepcopy(valid); r["attempts"].pop(); mutations.append(r)
        for key, value in (("success", 1), ("passed", 1), ("latency_ms", float("nan")),
                           ("output_tokens", True), ("cost_usd", 0), ("requested_model", "other")):
            r = copy.deepcopy(valid); r["attempts"][0][key] = value; mutations.append(r)
        for r in mutations:
            with self.assertRaises(ValidationError): validate_report(r)

    def test_shortlist_then_observed_latency(self):
        result = recommend(fixture(), "debugging", "fix")
        self.assertEqual(result["shortlist"], ["model-a", "model-b"])
        result = recommend(fixture(3), "debugging", "fix")
        self.assertEqual(result["shortlist"], ["model-b"])
        self.assertEqual(result["selection_basis"], "lowest observed median in this run")
        r = fixture(); r["attempts"][0]["returned_model"] = "other"
        self.assertEqual(recommend(r, "debugging", "fix")["shortlist"], ["model-b"])
        with self.assertRaises(RecommendationError): recommend(fixture(), "architecture", "fix")

    def test_demo_cannot_be_relabeled_live(self):
        r = fixture()
        for c in r["candidates"]: c["provider"] = "demo"
        with self.assertRaises(ValidationError): validate_report(r)
