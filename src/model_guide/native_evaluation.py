"""Subscription CLI track. Never silently equate it with a direct API run."""
from copy import deepcopy
import re
import time
import uuid

from .evaluation import (ValidationError, _identifier, _finite_number, _positive_int,
                         validate_suite, suite_hash, median_latency)
from .native import NativeClient, NativeError, NATIVE_PROFILE
from .recommendations import RecommendationError
from .storage import read_json, reserve_output

PROVIDERS = ("codex-cli", "claude-cli")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
CATEGORIES = ("debugging", "code-review", "testing")


def _fields(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValidationError("invalid native fields")


def _bounded(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValidationError(f"{label} must be {low}..{high}")


def validate_native_config(config):
    _fields(config, ("version", "candidates"))
    _bounded(config["version"], 1, 1, "native config version")
    if type(config["candidates"]) is not list or not 1 <= len(config["candidates"]) <= 16:
        raise ValidationError("native config requires 1..16 candidates")
    normalized, seen = [], set()
    for value in config["candidates"]:
        _fields(value, ("id", "provider", "model", "effort"), ("timeout_seconds",))
        _identifier(value["id"], "candidate ID"); _identifier(value["model"], "model ID")
        if value["id"] in seen: raise ValidationError("duplicate native candidate")
        seen.add(value["id"])
        if value["provider"] not in PROVIDERS or value["effort"] not in EFFORTS:
            raise ValidationError("unsupported native provider/effort; ultra orchestration is not measured by this text pilot")
        candidate = deepcopy(value)
        candidate.setdefault("timeout_seconds", 120)
        _bounded(candidate["timeout_seconds"], 10, 600, "timeout_seconds")
        normalized.append(candidate)
    return {"version": 1, "candidates": normalized}


def build_native_report(suite, candidates, repetitions, runtime, attempts, completion_status="complete"):
    suite = validate_suite(suite)
    candidates = validate_native_config({"version": 1, "candidates": candidates})["candidates"]
    report = {"schema_version": 2, "track": "native-cli", "mode": "live", "run_id": str(uuid.uuid4()),
        "created_at": int(time.time()), "suite_hash": suite_hash(suite), "suite_version": suite["version"],
        "tasks": [{"id": task["id"], "category": task["category"]} for task in suite["tasks"]],
        "candidates": candidates, "runtime": deepcopy(runtime), "repetitions": repetitions,
        "planned_calls": len(candidates) * len(suite["tasks"]) * repetitions,
        "completion_status": completion_status, "generated_token_ceiling": None, "cost_usd": None,
        "provenance": {"kind": "subscription-cli"}, "attempts": deepcopy(attempts)}
    return validate_native_report(report)


def validate_native_report(report):
    _fields(report, ("schema_version", "track", "mode", "run_id", "created_at", "suite_hash", "suite_version",
        "tasks", "candidates", "runtime", "repetitions", "planned_calls", "completion_status",
        "generated_token_ceiling", "cost_usd", "provenance", "attempts"))
    _bounded(report["schema_version"], 2, 2, "native report version")
    _bounded(report["suite_version"], 1, 1, "suite version")
    _identifier(report["run_id"], "run ID"); _positive_int(report["created_at"], "created_at")
    if (report["track"] != "native-cli" or report["mode"] != "live"
        or report["provenance"] != {"kind": "subscription-cli"}
        or report["generated_token_ceiling"] is not None or report["cost_usd"] is not None):
        raise ValidationError("invalid native provenance or unsupported cost/token ceiling")
    if type(report["suite_hash"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", report["suite_hash"]):
        raise ValidationError("invalid suite hash")
    normalized = validate_native_config({"version": 1, "candidates": report["candidates"]})["candidates"]
    if normalized != report["candidates"]: raise ValidationError("native candidates must be normalized")
    by_id = {c["id"]: c for c in normalized}
    if type(report["runtime"]) is not dict or report["runtime"].keys() != by_id.keys():
        raise ValidationError("runtime metadata must cover candidates")
    for cid, runtime in report["runtime"].items():
        _fields(runtime, ("cli_version", "auth_method", "profile"))
        if runtime["profile"] != NATIVE_PROFILE:
            raise ValidationError("unsupported native runtime profile")
        version = runtime["cli_version"]
        if type(version) is not str or not re.fullmatch(r"[A-Za-z0-9 ._()+-]{1,128}", version):
            raise ValidationError("invalid CLI version")
        auth = "chatgpt" if by_id[cid]["provider"] == "codex-cli" else "claude-subscription"
        if runtime["auth_method"] != auth: raise ValidationError("native subscription authentication required")
    if type(report["tasks"]) is not list or not 1 <= len(report["tasks"]) <= 100:
        raise ValidationError("invalid native tasks")
    tasks = {}
    for task in report["tasks"]:
        _fields(task, ("id", "category")); _identifier(task["id"], "task ID")
        if task["id"] in tasks or task["category"] not in CATEGORIES:
            raise ValidationError("duplicate task or unsupported category")
        tasks[task["id"]] = task["category"]
    _bounded(report["repetitions"], 1, 10, "repetitions")
    _bounded(report["planned_calls"], 1, 1000, "planned calls")
    if report["planned_calls"] != len(by_id) * len(tasks) * report["repetitions"]:
        raise ValidationError("native call count mismatch")
    if report["completion_status"] not in ("complete", "incomplete") or type(report["attempts"]) is not list:
        raise ValidationError("invalid native completion/attempts")
    seen = set()
    for attempt in report["attempts"]:
        _fields(attempt, ("candidate_id", "task_id", "category", "repetition", "success", "passed",
            "latency_ms", "input_tokens", "output_tokens", "cost_usd", "requested_model", "returned_model"), ("error",))
        cid, tid = attempt["candidate_id"], attempt["task_id"]
        _identifier(cid, "candidate ID"); _identifier(tid, "task ID")
        if cid not in by_id or tid not in tasks or attempt["category"] != tasks[tid]:
            raise ValidationError("native attempt reference mismatch")
        _bounded(attempt["repetition"], 1, report["repetitions"], "repetition")
        key = cid, tid, attempt["repetition"]
        if key in seen: raise ValidationError("duplicate native attempt")
        seen.add(key)
        if (type(attempt["success"]) is not bool or type(attempt["passed"]) is not bool
            or (attempt["passed"] and not attempt["success"])):
            raise ValidationError("invalid native success/pass")
        if attempt["requested_model"] != by_id[cid]["model"]: raise ValidationError("requested model mismatch")
        model = attempt["returned_model"]
        if model is not None and (type(model) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", model)):
            raise ValidationError("invalid observed native model")
        _finite_number(attempt["latency_ms"], "latency_ms")
        for field in ("input_tokens", "output_tokens"):
            _positive_int(attempt[field], field, allow_none=True)
        if attempt["cost_usd"] is not None: raise ValidationError("native cost unknown")
        if "error" in attempt and (attempt["success"] or type(attempt["error"]) is not str or not 1 <= len(attempt["error"]) <= 256):
            raise ValidationError("invalid native error")
    expected = {(cid, tid, rep) for cid in by_id for tid in tasks for rep in range(1, report["repetitions"] + 1)}
    if not seen <= expected or (report["completion_status"] == "complete" and seen != expected):
        raise ValidationError("incomplete native attempt matrix")
    return report


def recommend_native(report, category, task_text):
    try: validate_native_report(report)
    except ValidationError as exc: raise RecommendationError(str(exc)) from None
    if report["completion_status"] != "complete": raise RecommendationError("native run incomplete")
    if category not in CATEGORIES: raise RecommendationError("unsupported category")
    environments = {(c["provider"], report["runtime"][c["id"]]["cli_version"], report["runtime"][c["id"]]["profile"])
                    for c in report["candidates"]}
    if len(environments) != 1: raise RecommendationError("native environments not comparable")
    evidence = []
    for candidate in report["candidates"]:
        rows = [a for a in report["attempts"] if a["candidate_id"] == candidate["id"]]
        if any(a["returned_model"] != candidate["model"] for a in rows): continue
        rows = [a for a in rows if a["category"] == category]
        distinct = len({a["task_id"] for a in rows})
        if distinct < 3: continue
        quality = sum(a["passed"] for a in rows) / len(rows)
        if quality < .8: continue
        evidence.append({"candidate_id": candidate["id"], "configuration": candidate, "quality": quality,
                         "unique_tasks": distinct, "attempts": len(rows),
                         "median_latency_ms": median_latency(a["latency_ms"] for a in rows)})
    if not evidence: raise RecommendationError("insufficient native quality or verified model identity evidence")
    basis = "eligible native shortlist; cost unknown"
    selected = evidence
    if report["repetitions"] >= 3:
        fastest = min(e["median_latency_ms"] for e in evidence)
        selected = [e for e in evidence if e["median_latency_ms"] == fastest]
        basis = "lowest observed median in this run"
    return {"status": "provisional", "category": category, "task": task_text, "selection_basis": basis,
        "shortlist": [e["candidate_id"] for e in selected], "evidence": evidence,
        "provenance": {"track": "native-cli", "run_id": report["run_id"], "suite_hash": report["suite_hash"],
                       "suite_version": report["suite_version"], "mode": "live", "kind": "subscription-cli"},
        "prompt": f"Solve the user's {category} task with its required output format: {task_text}"}


def command_evaluate_native(args):
    from .cli import bundled_suite
    from .evaluation import grade
    config = validate_native_config(read_json(args.config))
    suite = validate_suite(read_json(args.suite) if args.suite else bundled_suite())
    candidates = [c for c in config["candidates"] if c["provider"] == args.provider]
    if not candidates: raise ValidationError("no selected native candidates")
    _bounded(args.repetitions, 1, 10, "repetitions")
    _bounded(args.max_requests, 1, 1000, "max_requests")
    count = len(candidates) * len(suite["tasks"]) * args.repetitions
    if count > args.max_requests: raise ValidationError("planned native invocations exceed max_requests")
    if not args.live: raise ValidationError("native evaluation consumes subscription usage; requires --live")
    runtime, clients = {}, {}
    with reserve_output(args.output, args.force) as output:
        for candidate in candidates:
            client = NativeClient(candidate["provider"])
            runtime[candidate["id"]] = client.preflight(candidate)
            clients[candidate["id"]] = client
        # Check metadata before starting a model, rather than after consuming usage.
        build_native_report(suite, candidates, args.repetitions, runtime, [], "incomplete")
        for c in candidates:
            print(f"native {c['id']}: {c['provider']} model={c['model']} effort={c['effort']} timeout={c['timeout_seconds']}s")
        print(f"planned CLI invocations: {count}; internal provider requests/retries unknown; token ceiling unknown; cost unknown", flush=True)
        attempts, stopped = [], False
        for candidate in candidates:
            for task in suite["tasks"]:
                for repetition in range(1, args.repetitions + 1):
                    attempt = {"candidate_id": candidate["id"], "task_id": task["id"], "category": task["category"],
                        "repetition": repetition, "success": False, "passed": False, "input_tokens": None,
                        "output_tokens": None, "cost_usd": None, "requested_model": candidate["model"], "returned_model": None}
                    start = time.monotonic()
                    try:
                        result = clients[candidate["id"]].evaluate(candidate, task["prompt"])
                        attempt.update(success=True, passed=grade(result.text, task["grader"], task["expected"]),
                            returned_model=result.model, input_tokens=result.input_tokens, output_tokens=result.output_tokens)
                    except NativeError as exc:
                        attempt["error"] = str(exc)
                        stopped = True
                    attempt["latency_ms"] = round((time.monotonic() - start) * 1000, 3)
                    attempts.append(attempt)
                    print(f"{candidate['id']} / {task['id']} / {repetition}: {'pass' if attempt['passed'] else 'fail'}", flush=True)
                    if stopped: break
                if stopped: break
            if stopped: break
        report = build_native_report(suite, candidates, args.repetitions, runtime, attempts, "incomplete" if stopped else "complete")
        output.write_json(report)
    if stopped: raise NativeError("native evaluation stopped after failure; incomplete report saved")
    print(f"native complete: {len(attempts)} invocations; cost unknown")
