import hashlib
import json
import math
import time
import uuid
from copy import deepcopy
from datetime import date

_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
_CATEGORIES = {"debugging", "code-review", "testing"}
_PROVIDERS = {"demo", "openai", "anthropic"}
_EFFORTS = {
    "openai": {"none", "minimal", "low", "medium", "high", "xhigh", "max"},
    "anthropic": {"low", "medium", "high", "xhigh", "max"},
}

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
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValidationError(f"{label} must be a finite nonnegative number")

def _json_value(value):
    if value is None or type(value) is bool or isinstance(value, str):
        return True
    if type(value) is int:
        return True
    if type(value) is float:
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_value(item) for key, item in value.items())
    return False

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
    try:
        actual = json.loads(text)
        if grader not in ("exact", "json_subset") or not _json_value(actual) or not _json_value(expected):
            return False
        return _strict_equal(actual, expected) if grader == "exact" else _subset(actual, expected)
    except (TypeError, ValueError, RecursionError, OverflowError):
        return False

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
        if not isinstance(prompt,str) or not prompt.strip() or len(prompt.encode())>16384 or grader not in ("exact","json_subset") or not _json_value(task["expected"]): raise ValidationError("invalid task")
        total += len(prompt.encode())
    if total>1048576: raise ValidationError("suite prompts exceed 1 MiB")
    return suite

def validate_config(config):
    if not isinstance(config, dict) or set(config) != {"version", "candidates"} or type(config.get("version")) is not int or config["version"] != 1: raise ValidationError("config requires version 1")
    candidates=config.get("candidates")
    if not isinstance(candidates,list) or not candidates or len(candidates)>16: raise ValidationError("config needs 1..16 candidates")
    ids=set()
    normalized = []
    for c in candidates:
        if not isinstance(c,dict) or set(c) - {"id", "provider", "model", "max_output_tokens", "effort", "prices"}: raise ValidationError("invalid candidate fields")
        _identifier(c.get("id"), "candidate ID")
        if c["id"] in ids: raise ValidationError("candidate IDs must be unique")
        ids.add(c["id"])
        _enum(c.get("provider"), _PROVIDERS, "candidate provider")
        _identifier(c.get("model"), "model ID")
        cap=c.get("max_output_tokens",1024)
        if type(cap) is not int or not 1<=cap<=32768: raise ValidationError("max_output_tokens must be 1..32768")
        if "effort" in c:
            if c["provider"] == "demo" or not isinstance(c["effort"], str) or c["effort"] not in _EFFORTS[c["provider"]]: raise ValidationError("invalid native API effort")
        if "prices" in c:
            prices=c["prices"]
            if not isinstance(prices,dict) or set(prices) != {"as_of", "input_per_million", "output_per_million"}: raise ValidationError("invalid prices metadata")
            if not isinstance(prices["as_of"], str): raise ValidationError("prices as_of must be YYYY-MM-DD")
            try: date.fromisoformat(prices["as_of"])
            except ValueError as exc: raise ValidationError("prices as_of must be YYYY-MM-DD") from exc
            _finite_number(prices["input_per_million"], "input_per_million")
            _finite_number(prices["output_per_million"], "output_per_million")
        candidate = deepcopy(c)
        candidate["max_output_tokens"] = cap
        normalized.append(candidate)
    return {"version": 1, "candidates": normalized}

def suite_hash(suite): return hashlib.sha256(json.dumps(suite,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def build_report(suite, candidates, repetitions, attempts, mode):
    suite = deepcopy(validate_suite(suite))
    candidates = validate_config({"version": 1, "candidates": candidates})["candidates"]
    if type(repetitions) is not int or not 1 <= repetitions <= 10: raise ValidationError("repetitions must be 1..10")
    if mode not in {"live", "synthetic"}: raise ValidationError("invalid report mode")
    planned_calls = len(candidates) * len(suite["tasks"]) * repetitions
    report = {
        "schema_version": 1, "run_id": str(uuid.uuid4()), "created_at": int(time.time()),
        "suite_hash": suite_hash(suite), "suite_version": suite["version"],
        "tasks": [{"id": task["id"], "category": task["category"]} for task in suite["tasks"]],
        "candidates": candidates, "repetitions": repetitions, "planned_calls": planned_calls,
        "generated_token_ceiling": sum(candidate.get("max_output_tokens", 1024) for candidate in candidates) * len(suite["tasks"]) * repetitions,
        "completion_status": "complete", "mode": mode,
        "provenance": {"kind": "synthetic-demo" if mode == "synthetic" else "live-api"},
        "attempts": deepcopy(attempts),
    }
    validate_report(report)
    return deepcopy(report)

def validate_report(report):
    required = {"schema_version", "run_id", "created_at", "suite_hash", "suite_version", "tasks", "candidates", "repetitions", "planned_calls", "generated_token_ceiling", "completion_status", "mode", "provenance", "attempts"}
    if not isinstance(report, dict) or set(report) != required: raise ValidationError("invalid report fields")
    if type(report["schema_version"]) is not int or report["schema_version"] != 1 or type(report["suite_version"]) is not int or report["suite_version"] != 1: raise ValidationError("unsupported report schema")
    if not isinstance(report["run_id"], str) or not report["run_id"] or type(report["created_at"]) is not int or report["created_at"] < 0: raise ValidationError("invalid report identity")
    if not isinstance(report["suite_hash"], str) or len(report["suite_hash"]) != 64 or any(char not in "0123456789abcdef" for char in report["suite_hash"]): raise ValidationError("invalid suite hash")
    if not isinstance(report["tasks"], list) or not report["tasks"] or len(report["tasks"]) > 100: raise ValidationError("invalid report tasks")
    tasks = {}
    for task in report["tasks"]:
        if not isinstance(task, dict) or set(task) != {"id", "category"}: raise ValidationError("invalid task manifest entry")
        _identifier(task.get("id"), "task ID")
        _enum(task["category"], _CATEGORIES, "task category")
        if task["id"] in tasks: raise ValidationError("invalid task manifest entry")
        tasks[task["id"]] = task["category"]
    normalized = validate_config({"version": 1, "candidates": report["candidates"]})
    if normalized["candidates"] != report["candidates"]: raise ValidationError("report candidates are not normalized")
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
    if (report["mode"] == "synthetic" and providers != {"demo"}) or (report["mode"] == "live" and "demo" in providers): raise ValidationError("mode and candidate provenance disagree")
    if not isinstance(report["attempts"], list): raise ValidationError("invalid attempts")
    seen = set()
    for attempt in report["attempts"]:
        _validate_attempt(attempt, candidates, tasks, report["repetitions"], seen)
    expected_tuples = {(candidate_id, task_id, repetition) for candidate_id in candidates for task_id in tasks for repetition in range(1, report["repetitions"] + 1)}
    if report["completion_status"] == "complete" and seen != expected_tuples: raise ValidationError("report has incomplete attempt matrix")
    return report

def _validate_attempt(attempt, candidates, tasks, repetitions, seen):
    required = {"candidate_id", "task_id", "category", "repetition", "success", "passed", "latency_ms", "input_tokens", "output_tokens", "cost_usd", "requested_model", "returned_model"}
    if not isinstance(attempt, dict) or set(attempt) - (required | {"error"}) or not required <= set(attempt): raise ValidationError("invalid attempt fields")
    candidate_id, task_id = attempt["candidate_id"], attempt["task_id"]
    _identifier(candidate_id, "candidate ID")
    _identifier(task_id, "task ID")
    if candidate_id not in candidates or task_id not in tasks or attempt["category"] != tasks[task_id]: raise ValidationError("attempt does not match report manifest")
    if type(attempt["repetition"]) is not int or not 1 <= attempt["repetition"] <= repetitions: raise ValidationError("invalid attempt repetition")
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
