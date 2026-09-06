import importlib.resources
import json
import unittest


def hard_suite():
    resource = importlib.resources.files("model_guide.data").joinpath("programming-hard.json")
    return json.loads(resource.read_text(encoding="utf-8"))


class HardReviewOracleTest(unittest.TestCase):
    def test_hard_review_answer_keys_match_independent_toy_oracles(self):
        tasks = {
            task["id"]: task for task in hard_suite()["tasks"]
            if task["id"].startswith("hard-review-")
        }
        self.assertEqual(set(tasks), {"hard-review-1", "hard-review-2", "hard-review-3", "hard-review-4"})
        self.assertTrue(all(task["category"] == "code-review" and task["grader"] == "exact" for task in tasks.values()))

        roles = ("owner", "editor", "viewer")
        q_false_positives = []
        equivalent = []
        candidates = {
            "P": lambda active, tenant, role: active and tenant and role in {"owner", "editor"},
            "Q": lambda active, tenant, role: active and (tenant or role in {"owner", "editor"}),
            "R": lambda active, tenant, role: active and tenant and (role == "owner" or role == "editor"),
        }
        vectors = [(active, tenant, role) for active in (False, True) for tenant in (False, True) for role in roles]
        specified = [active and tenant and role in {"owner", "editor"} for active, tenant, role in vectors]
        for name, predicate in candidates.items():
            observed = [predicate(active, tenant, role) for active, tenant, role in vectors]
            if observed == specified:
                equivalent.append(name)
            if name == "Q":
                q_false_positives = [
                    f"active={str(active).lower()},tenant_match={str(tenant).lower()},role={role}"
                    for (active, tenant, role), actual, expected in zip(vectors, observed, specified)
                    if actual and not expected
                ]
        auth_oracle = {"equivalent_to_spec": equivalent, "q_false_positive_vectors": q_false_positives, "vector_count": len(vectors)}

        backend = {("north:west", "7"): "A", ("north", "west:7"): "B", ("north", "7"): "C"}
        calls = (("north:west", "7"), ("north", "west:7"), ("north", "7"))
        string_cache, tuple_cache, string_returns, tuple_returns = {}, {}, [], []
        for tenant, user in calls:
            joined = tenant + ":" + user
            string_cache.setdefault(joined, backend[(tenant, user)])
            tuple_cache.setdefault((tenant, user), backend[(tenant, user)])
            string_returns.append(string_cache[joined])
            tuple_returns.append(tuple_cache[(tenant, user)])
        cache_oracle = {
            "string_key_returns": string_returns,
            "tuple_key_returns": tuple_returns,
            "mismatched_call_indexes": [i for i, values in enumerate(zip(string_returns, tuple_returns)) if values[0] != values[1]],
            "collision_key": calls[0][0] + ":" + calls[0][1],
        }

        def run_interleaving(comparator, stale):
            state, commits = {"balance": 10, "version": 0}, []
            first = (state["balance"], state["version"])
            second = first if stale else None
            for name, observed in (("T1", first), ("T2", second)):
                if observed is None:
                    observed = (state["balance"], state["version"])
                balance, version = observed
                if comparator(state["version"], version) and balance >= 7:
                    state["balance"] = balance - 7
                    state["version"] += 1
                    commits.append(name)
            return {"commits": commits, "balance": state["balance"], "version": state["version"]}

        cas_oracle = {
            "buggy_stale": run_interleaving(lambda actual, observed: actual >= observed, True),
            "fixed_stale": run_interleaving(lambda actual, observed: actual == observed, True),
            "buggy_fresh": run_interleaving(lambda actual, observed: actual >= observed, False),
            "fixed_fresh": run_interleaving(lambda actual, observed: actual == observed, False),
        }

        inputs = ("docs/readme", "docs/../secret", "docs//readme", "./docs", "../secret")

        def valid(components):
            return all(component not in ("", ".", "..") for component in components)

        def normalize(raw):
            output = []
            for component in raw.split("/"):
                if component in ("", "."):
                    continue
                if component == "..":
                    if output:
                        output.pop()
                    continue
                output.append(component)
            return output

        accepted_spec = [raw for raw in inputs if valid(raw.split("/"))]
        accepted_a = [raw for raw in inputs if valid(raw.split("/"))]
        accepted_b = [raw for raw in inputs if valid(normalize(raw))]
        path_oracle = {
            "accepted_by_spec": accepted_spec,
            "accepted_by_A": accepted_a,
            "accepted_by_B": accepted_b,
            "b_false_positives": [raw for raw in accepted_b if raw not in accepted_spec],
        }

        self.assertEqual(tasks["hard-review-1"]["expected"], auth_oracle)
        self.assertEqual(tasks["hard-review-2"]["expected"], cache_oracle)
        self.assertEqual(tasks["hard-review-3"]["expected"], cas_oracle)
        self.assertEqual(tasks["hard-review-4"]["expected"], path_oracle)


if __name__ == "__main__":
    unittest.main()
