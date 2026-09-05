import unittest
from model_guide.recommendations import recommend, RecommendationError


class RecommendationTest(unittest.TestCase):
    def test_demo_and_incomplete_are_rejected(self):
        demo = {"schema_version":1,"mode":"synthetic","completion_status":"complete","attempts":[]}
        with self.assertRaises(RecommendationError): recommend(demo, "debugging", "task")
        incomplete = {"schema_version":1,"mode":"live","completion_status":"incomplete","attempts":[]}
        with self.assertRaises(RecommendationError): recommend(incomplete, "debugging", "task")
