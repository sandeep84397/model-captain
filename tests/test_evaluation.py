import unittest
import json
from collections import Counter
from model_guide.cli import bundled_suite
from model_guide.evaluation import grade, validate_suite, ValidationError


class EvaluationTest(unittest.TestCase):
    def test_strict_grading_and_suite_validation(self):
        self.assertTrue(grade("true", "exact", True))
        self.assertFalse(grade("1", "exact", True))
        self.assertTrue(grade('{"a":1,"b":2}', "json_subset", {"a":1}))
        self.assertFalse(grade('{"a":true}', "json_subset", {"a":1}))
        with self.assertRaises(ValidationError): validate_suite({"version":1,"tasks":[]})

    def test_bundled_tasks_are_diagnostic_not_answer_echoes(self):
        suite = validate_suite(bundled_suite())
        self.assertEqual(Counter(t["category"] for t in suite["tasks"]),
                         {"debugging": 3, "code-review": 3, "testing": 3})
        for task in suite["tasks"]:
            self.assertGreater(len(task["prompt"].splitlines()), 3)
            self.assertIn("Return JSON", task["prompt"])
            # Regression for the original full-reference-in-prompt defect.
            reference = json.dumps(task["expected"], separators=(",", ":"))
            self.assertNotIn(reference, task["prompt"].replace(" ", ""))
            self.assertTrue(grade(reference, task["grader"], task["expected"]))
