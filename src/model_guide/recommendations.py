from collections import defaultdict
from statistics import median
from .evaluation import ValidationError, validate_report

class RecommendationError(ValueError): pass

def recommend(report, category, task_text):
    try:
        validate_report(report)
    except ValidationError as exc:
        raise RecommendationError(str(exc)) from exc
    if report["mode"] == "synthetic": raise RecommendationError("demo results are demonstration-only")
    if report["completion_status"] != "complete": raise RecommendationError("run is incomplete")
    attempts=report["attempts"]
    categories = {task["category"] for task in report["tasks"]}
    if category not in categories: raise RecommendationError("no eligible attempts for category")
    mismatched = {row["candidate_id"] for row in attempts if row["requested_model"] != row["returned_model"]}
    by=defaultdict(list)
    for a in attempts:
        if a["category"] == category and a["candidate_id"] not in mismatched:
            by[a["candidate_id"]].append(a)
    eligible=[]
    for candidate in report["candidates"]:
        cid = candidate["id"]
        rows = by[cid]
        tasks={x.get("task_id") for x in rows}
        if len(tasks)<3: continue
        if len(rows) != len(tasks) * report.get("repetitions",0): continue
        quality=sum(bool(x.get("passed")) for x in rows)/len(rows)
        if quality>=.8: eligible.append((cid,quality,len(tasks),len(rows),median(x["latency_ms"] for x in rows)))
    if not eligible: raise RecommendationError("insufficient comparable evidence")
    if report["repetitions"] < 3:
        selected = eligible
        basis = "all eligible candidates; fewer than three repetitions"
    else:
        fastest = min(entry[4] for entry in eligible)
        selected = [entry for entry in eligible if entry[4] == fastest]
        basis = "lowest observed median in this run"
    candidates = {candidate["id"]: candidate for candidate in report["candidates"]}
    return {"status":"provisional","category":category,"task":task_text,"selection_basis":basis,"shortlist":[x[0] for x in selected],"evidence":[{"candidate_id":x[0],"configuration":candidates[x[0]],"quality":x[1],"unique_tasks":x[2],"attempts":x[3],"median_latency_ms":x[4]} for x in selected],"prompt":f"Solve only this {category} microtask. Return required JSON only: {task_text}"}
