from collections import defaultdict

class RecommendationError(ValueError): pass

def recommend(report, category, task_text):
    if report.get("schema_version") != 1: raise RecommendationError("unsupported report schema")
    if report.get("mode") == "synthetic": raise RecommendationError("demo results are demonstration-only")
    if report.get("completion_status") != "complete": raise RecommendationError("run is incomplete")
    attempts=report.get("attempts")
    if not isinstance(attempts,list): raise RecommendationError("invalid attempts")
    by=defaultdict(list)
    for a in attempts:
        if not isinstance(a,dict) or a.get("category") != category: continue
        if not a.get("success") or a.get("requested_model") != a.get("returned_model"): continue
        by[a.get("candidate_id")].append(a)
    if not by: raise RecommendationError("no eligible attempts for category")
    eligible=[]
    for cid, rows in by.items():
        tasks={x.get("task_id") for x in rows}
        if len(tasks)<3: continue
        if len(rows) != len(tasks) * report.get("repetitions",0): continue
        quality=sum(bool(x.get("passed")) for x in rows)/len(rows)
        if quality>=.8: eligible.append((cid,quality,len(tasks),len(rows)))
    if not eligible: raise RecommendationError("insufficient comparable evidence")
    best=max(x[1] for x in eligible)
    selected=[x for x in eligible if x[1]==best]
    return {"status":"provisional","category":category,"task":task_text,"shortlist":[x[0] for x in selected],"evidence":[{"candidate_id":x[0],"quality":x[1],"unique_tasks":x[2],"attempts":x[3]} for x in selected],"prompt":f"Solve only this {category} microtask. Return required JSON only: {task_text}"}
