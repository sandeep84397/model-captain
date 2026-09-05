import hashlib
import json
import math
import time
import uuid

class ValidationError(ValueError): pass

def _strict_equal(left, right):
    return type(left) is type(right) and left == right

def _subset(actual, expected):
    if isinstance(expected, dict): return isinstance(actual, dict) and all(k in actual and _subset(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list): return isinstance(actual, list) and len(actual) == len(expected) and all(_subset(a, b) for a,b in zip(actual, expected))
    return _strict_equal(actual, expected)

def grade(text, grader, expected):
    try: actual = json.loads(text)
    except (TypeError, json.JSONDecodeError): return False
    return _strict_equal(actual, expected) if grader == "exact" else _subset(actual, expected)

def validate_suite(suite):
    if not isinstance(suite, dict) or type(suite.get("version")) is not int: raise ValidationError("suite requires integer version")
    tasks=suite.get("tasks")
    if not isinstance(tasks,list) or not tasks or len(tasks)>100: raise ValidationError("suite tasks must contain 1..100 entries")
    ids=set(); total=0
    for task in tasks:
        if not isinstance(task,dict) or not isinstance(task.get("id"),str) or not task["id"].strip() or task["id"] in ids: raise ValidationError("task IDs must be unique and nonempty")
        ids.add(task["id"]); prompt=task.get("prompt"); grader=task.get("grader")
        if not isinstance(prompt,str) or len(prompt.encode())>16384 or grader not in ("exact","json_subset") or "expected" not in task: raise ValidationError("invalid task")
        total += len(prompt.encode())
    if total>1048576: raise ValidationError("suite prompts exceed 1 MiB")
    return suite

def validate_config(config):
    candidates=config.get("candidates") if isinstance(config,dict) else None
    if not isinstance(candidates,list) or not candidates or len(candidates)>16: raise ValidationError("config needs 1..16 candidates")
    ids=set()
    for c in candidates:
        if not isinstance(c,dict) or not isinstance(c.get("id"),str) or not c["id"].strip() or c["id"] in ids: raise ValidationError("candidate IDs must be unique")
        ids.add(c["id"])
        if c.get("provider") not in ("demo","openai","anthropic") or not isinstance(c.get("model"),str) or not c["model"]: raise ValidationError("invalid candidate provider/model")
        cap=c.get("max_output_tokens",1024)
        if type(cap) is not int or not 1<=cap<=32768: raise ValidationError("max_output_tokens must be 1..32768")
        if c.get("effort") == "ultra": raise ValidationError("ultra is unsupported native API effort")
        prices=c.get("prices",{})
        if not isinstance(prices,dict): raise ValidationError("prices must be object")
        for value in prices.values():
            if type(value) not in (int,float) or isinstance(value,bool) or not math.isfinite(value) or value<0: raise ValidationError("prices must be finite nonnegative numbers")
    return config

def suite_hash(suite): return hashlib.sha256(json.dumps(suite,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def build_report(suite, candidates, repetitions, attempts, mode):
    return {"schema_version":1,"run_id":str(uuid.uuid4()),"created_at":int(time.time()),"suite_hash":suite_hash(suite),"suite_version":suite["version"],"candidates":candidates,"repetitions":repetitions,"planned_calls":len(candidates)*len(suite["tasks"])*repetitions,"completion_status":"complete","mode":mode,"attempts":attempts}
