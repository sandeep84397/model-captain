import unittest
from model_guide.evaluation import grade, validate_suite, ValidationError


class EvaluationTest(unittest.TestCase):
    def test_strict_grading_and_suite_validation(self):
        self.assertTrue(grade("true", "exact", True))
        self.assertFalse(grade("1", "exact", True))
        self.assertTrue(grade('{"a":1,"b":2}', "json_subset", {"a":1}))
        self.assertFalse(grade('{"a":true}', "json_subset", {"a":1}))
        with self.assertRaises(ValidationError): validate_suite({"version":1,"tasks":[]})
