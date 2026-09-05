import hashlib
import json
import math
import time
import uuid

_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
_CATEGORIES = {"debugging", "code-review", "testing"}
_PROVIDERS = {"demo", "openai", "anthropic"}
_EFFORTS = {"low", "medium", "high", "xhigh"}

class ValidationError(ValueError): pass

def _strict_equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_strict_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_strict_equal(a, b) for a, b in zip(left, right))
    return left == right

def _identifier(value, label):
    if not isinstance(value, str) or not value or len(value) > 128 or any(char not in _ID_CHARS for char in value):
        raise ValidationError(f"invalid {label}")

def _enum(value, allowed, label):
    if not isinstance(value, str) or value not in allowed:
        raise ValidationError(f"invalid {label}")

def _finite_number(value, label, allow_none=False):
    if value is None and allow_none:
        return
    if type(value) not in (int, float) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValidationError(f"{label} must be a finite nonnegative number")

def _positive_int(value, label, allow_none=False):
    if value is None and allow_none:
        return
    if type(value) is not int or value < 0:
        raise ValidationError(f"{label} must be a nonnegative integer")

def _subset(actual, expected):
    if isinstance(expected, dict): return isinstance(actual, dict) and all(k in actual and _subset(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list): return isinstance(actual, list) and len(actual) == len(expected) and all(_subset(a, b) for a,b in zip(actual, expected))
    return _strict_equal(actual, expected)

def grade(text, grader, expected):
    try: actual = json.loads(text)
    except (TypeError, json.JSONDecodeError): return False
    return _strict_equal(actual, expected) if grader == "exact" else _subset(actual, expected)

def validate_suite(suite):
    if not isinstance(suite, dict) or set(suite) != {"version", "tasks"} or type(suite.get("version")) is not int or suite["version"] != 1: raise ValidationError("suite requires version 1")
    tasks=suite.get("tasks")
    if not isinstance(tasks,list) or not tasks or len(tasks)>100: raise ValidationError("suite tasks must contain 1..100 entries")
    ids=set(); total=0
    for task in tasks:
        if not isinstance(task,dict) or set(task) != {"id", "category", "prompt", "grader", "expected"}: raise ValidationError("invalid task")
        _identifier(task.get("id"), "task ID")
        if task["id"] in ids: raise ValidationError("task IDs must be unique")
        ids.add(task["id"]); prompt=task.get("prompt"); grader=task.get("grader")
        _enum(task.get("category"), _CATEGORIES, "task category")
        if not isinstance(prompt,str) or len(prompt.encode())>16384 or grader not in ("exact","json_subset"): raise ValidationError("invalid task")
        total += len(prompt.encode())
    if total>1048576: raise ValidationError("suite prompts exceed 1 MiB")
    return suite

def validate_config(config):
    if not isinstance(config, dict) or set(config) != {"version", "candidates"} or type(config.get("version")) is not int or config["version"] != 1: raise ValidationError("config requires version 1")
    candidates=config.get("candidates")
    if not isinstance(candidates,list) or not candidates or len(candidates)>16: raise ValidationError("config needs 1..16 candidates")
    ids=set()
    for c in candidates:
        if not isinstance(c,dict) or set(c) - {"id", "provider", "model", "max_output_tokens", "effort", "prices"}: raise ValidationError("invalid candidate fields")
        _identifier(c.get("id"), "candidate ID")
        if c["id"] in ids: raise ValidationError("candidate IDs must be unique")
        ids.add(c["id"])
        _enum(c.get("provider"), _PROVIDERS, "candidate provider")
        if not isinstance(c.get("model"),str) or not c["model"] or len(c["model"]) > 256: raise ValidationError("invalid candidate provider/model")
        cap=c.get("max_output_tokens",1024)
        if type(cap) is not int or not 1<=cap<=32768: raise ValidationError("max_output_tokens must be 1..32768")
        if "effort" in c and (not isinstance(c["effort"], str) or c["effort"] not in _EFFORTS): raise ValidationError("invalid native API effort")
        if "prices" in c:
            prices=c["prices"]
            if not isinstance(prices,dict) or set(prices) != {"as_of", "input_per_million", "output_per_million"}: raise ValidationError("invalid prices metadata")
            if not isinstance(prices["as_of"], str) or len(prices["as_of"]) != 10 or prices["as_of"][4:5] != "-" or prices["as_of"][7:8] != "-": raise ValidationError("prices as_of must be YYYY-MM-DD")
            _finite_number(prices["input_per_million"], "input_per_million")
            _finite_number(prices["output_per_million"], "output_per_million")
    return config

def suite_hash(suite): return hashlib.sha256(json.dumps(suite,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def build_report(suite, candidates, repetitions, attempts, mode):
    validate_suite(suite)
    validate_config({"version": 1, "candidates": candidates})
    if type(repetitions) is not int or not 1 <= repetitions <= 10: raise ValidationError("repetitions must be 1..10")
    if mode not in {"live", "synthetic"}: raise ValidationError("invalid report mode")
    planned_calls = len(candidates) * len(suite["tasks"]) * repetitions
    return {
        "schema_version": 1, "run_id": str(uuid.uuid4()), "created_at": int(time.time()),
        "suite_hash": suite_hash(suite), "suite_version": suite["version"], "task_manifest": {
            "tasks": [{"id": task["id"], "category": task["category"]} for task in suite["tasks"]]},
        "candidates": candidates, "repetitions": repetitions, "planned_calls": planned_calls,
        "generated_token_ceiling": sum(candidate.get("max_output_tokens", 1024) for candidate in candidates) * len(suite["tasks"]) * repetitions,
        "completion_status": "complete", "mode": mode,
        "provenance": {"kind": "synthetic-demo" if mode == "synthetic" else "live-api"},
        "attempts": attempts,
    }

def validate_report(report):
    required = {"schema_version", "run_id", "created_at", "suite_hash", "suite_version", "task_manifest", "candidates", "repetitions", "planned_calls", "generated_token_ceiling", "completion_status", "mode", "provenance", "attempts"}
    if not isinstance(report, dict) or set(report) != required: raise ValidationError("invalid report fields")
    if type(report["schema_version"]) is not int or report["schema_version"] != 1 or type(report["suite_version"]) is not int or report["suite_version"] != 1: raise ValidationError("unsupported report schema")
    if not isinstance(report["run_id"], str) or not report["run_id"] or type(report["created_at"]) is not int or report["created_at"] < 0: raise ValidationError("invalid report identity")
    if not isinstance(report["suite_hash"], str) or len(report["suite_hash"]) != 64 or any(char not in "0123456789abcdef" for char in report["suite_hash"]): raise ValidationError("invalid suite hash")
    manifest = report["task_manifest"]
    if not isinstance(manifest, dict) or set(manifest) != {"tasks"} or not isinstance(manifest["tasks"], list) or not manifest["tasks"] or len(manifest["tasks"]) > 100: raise ValidationError("invalid task manifest")
    tasks = {}
    for task in manifest["tasks"]:
        if not isinstance(task, dict) or set(task) != {"id", "category"}: raise ValidationError("invalid task manifest entry")
        _identifier(task.get("id"), "task ID")
        _enum(task["category"], _CATEGORIES, "task category")
        if task["id"] in tasks: raise ValidationError("invalid task manifest entry")
        tasks[task["id"]] = task["category"]
    validate_config({"version": 1, "candidates": report["candidates"]})
    candidates = {candidate["id"]: candidate for candidate in report["candidates"]}
    if type(report["repetitions"]) is not int or not 1 <= report["repetitions"] <= 10: raise ValidationError("invalid repetitions")
    expected_calls = len(tasks) * len(candidates) * report["repetitions"]
    if type(report["planned_calls"]) is not int or report["planned_calls"] != expected_calls: raise ValidationError("invalid planned calls")
    expected_ceiling = sum(candidate.get("max_output_tokens", 1024) for candidate in candidates.values()) * len(tasks) * report["repetitions"]
    if type(report["generated_token_ceiling"]) is not int or report["generated_token_ceiling"] != expected_ceiling: raise ValidationError("invalid generated token ceiling")
    _enum(report["completion_status"], {"complete", "incomplete"}, "report status")
    _enum(report["mode"], {"live", "synthetic"}, "report mode")
    if not isinstance(report["provenance"], dict) or set(report["provenance"]) != {"kind"} or report["provenance"]["kind"] != ("synthetic-demo" if report["mode"] == "synthetic" else "live-api"): raise ValidationError("invalid report provenance")
    providers = {candidate["provider"] for candidate in candidates.values()}
    if (report["mode"] == "synthetic") != (providers == {"demo"}): raise ValidationError("mode and candidate provenance disagree")
    if not isinstance(report["attempts"], list): raise ValidationError("invalid attempts")
    seen = set()
    for attempt in report["attempts"]:
        _validate_attempt(attempt, candidates, tasks, seen)
    if report["completion_status"] == "complete" and len(seen) != expected_calls: raise ValidationError("report has incomplete attempt matrix")
    return report

def _validate_attempt(attempt, candidates, tasks, seen):
    required = {"candidate_id", "task_id", "category", "repetition", "success", "passed", "latency_ms", "input_tokens", "output_tokens", "cost_usd", "requested_model", "returned_model"}
    if not isinstance(attempt, dict) or set(attempt) - (required | {"error"}) or not required <= set(attempt): raise ValidationError("invalid attempt fields")
    candidate_id, task_id = attempt["candidate_id"], attempt["task_id"]
    _identifier(candidate_id, "candidate ID")
    _identifier(task_id, "task ID")
    if candidate_id not in candidates or task_id not in tasks or attempt["category"] != tasks[task_id]: raise ValidationError("attempt does not match report manifest")
    if type(attempt["repetition"]) is not int or not 1 <= attempt["repetition"] <= 10: raise ValidationError("invalid attempt repetition")
    key = (candidate_id, task_id, attempt["repetition"])
    if key in seen: raise ValidationError("duplicate attempt")
    seen.add(key)
    if type(attempt["success"]) is not bool or type(attempt["passed"]) is not bool or attempt["requested_model"] != candidates[candidate_id]["model"]: raise ValidationError("invalid attempt result")
    if attempt["returned_model"] is not None and not isinstance(attempt["returned_model"], str): raise ValidationError("invalid returned model")
    _finite_number(attempt["latency_ms"], "latency_ms")
    _positive_int(attempt["input_tokens"], "input_tokens", allow_none=True)
    _positive_int(attempt["output_tokens"], "output_tokens", allow_none=True)
    if attempt["cost_usd"] is not None: raise ValidationError("monetary costs are unsupported")
    if not attempt["success"] and attempt["passed"]: raise ValidationError("failed attempts cannot pass")
    if "error" in attempt and (attempt["success"] or not isinstance(attempt["error"], str) or not attempt["error"]): raise ValidationError("invalid attempt error")
