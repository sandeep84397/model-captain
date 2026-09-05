import argparse, json, os, sys, time
from importlib.resources import files
from pathlib import Path
from . import DISPLAY_NAME
from .config import STARTER_CONFIG, load_config
from .evaluation import ValidationError, build_report, grade, validate_suite, validate_report, median_latency
from .recommendations import RecommendationError, recommend
from .providers import AnthropicProvider, OpenAIProvider, ProviderError, StdlibTransport
from .storage import StorageError, atomic_json, atomic_text, read_json, reserve_output

def bundled_suite(): return json.loads(files("model_guide.data").joinpath("programming.json").read_text())
def _demo_output(task): return json.dumps(task["expected"], separators=(",",":"))
def command_init(args): atomic_json(args.config, STARTER_CONFIG); print(f"wrote {args.config}")
def command_evaluate(args):
    suite=validate_suite(read_json(args.suite) if args.suite else bundled_suite()); config=load_config(read_json(args.config))
    candidates=[c for c in config["candidates"] if args.provider == "all" and c["provider"] != "demo" or c["provider"] == args.provider]
    if not candidates: raise ValidationError("no selected candidates")
    if type(args.repetitions) is not int or not 1<=args.repetitions<=10: raise ValidationError("repetitions must be 1..10")
    calls=len(suite["tasks"])*len(candidates)*args.repetitions
    if type(args.max_requests) is not int or not 1 <= args.max_requests <= 1000 or calls > args.max_requests:
        raise ValidationError("planned calls exceed max requests or invalid request cap")
    live_candidates=[c for c in candidates if c["provider"] != "demo"]
    if live_candidates and not args.live: raise ValidationError("live providers require --live")
    providers={}
    if live_candidates:
        transport=StdlibTransport()
        for candidate in live_candidates:
            key_name="OPENAI_API_KEY" if candidate["provider"]=="openai" else "ANTHROPIC_API_KEY"
            key=os.environ.get(key_name)
            if not key: raise ValidationError(f"{key_name} is required for selected candidate")
            providers[candidate["id"]]=OpenAIProvider(key,transport) if candidate["provider"]=="openai" else AnthropicProvider(key,transport)
    with reserve_output(args.output, args.force) as output:
        for candidate in candidates:
            print(f"candidate {candidate['id']}: provider={candidate['provider']} model={candidate['model']} "
                  f"effort={candidate.get('effort', 'provider-default')} max_output_tokens={candidate['max_output_tokens']}")
        ceiling = sum(c["max_output_tokens"] for c in candidates) * len(suite["tasks"]) * args.repetitions
        print(f"planned calls: {calls}; generated-token ceiling: {ceiling}; cost unknown", flush=True)
        attempts = []
        for candidate in candidates:
            for task in suite["tasks"]:
                for repetition in range(1, args.repetitions + 1):
                    started = time.monotonic()
                    attempt = {"candidate_id": candidate["id"], "task_id": task["id"],
                        "category": task["category"], "repetition": repetition,
                        "success": False, "passed": False, "input_tokens": None, "output_tokens": None,
                        "requested_model": candidate["model"], "returned_model": None, "cost_usd": None}
                    try:
                        if candidate["provider"] == "demo":
                            text = _demo_output(task)
                            attempt["returned_model"] = candidate["model"]
                        else:
                            result = providers[candidate["id"]].evaluate(candidate, task["prompt"], task)
                            text = result.text
                            attempt.update(returned_model=result.model, input_tokens=result.input_tokens,
                                           output_tokens=result.output_tokens)
                        attempt.update(success=True, passed=grade(text, task["grader"], task["expected"]))
                    except ProviderError as exc:
                        attempt.update(error=str(exc), returned_model=getattr(exc, "model", None),
                            input_tokens=getattr(exc, "input_tokens", None), output_tokens=getattr(exc, "output_tokens", None))
                    attempt["latency_ms"] = round((time.monotonic() - started) * 1000, 3)
                    attempts.append(attempt)
        mode = "synthetic" if not live_candidates else "live"
        report = build_report(suite, candidates, args.repetitions, attempts, mode)
        output.write_json(report)
    print(f"{mode} complete: {calls} calls; cost unknown")
def command_report(args):
    r=validate_report(read_json(args.input)); attempts=r["attempts"]
    print(f"run {r.get('run_id')} {r.get('completion_status')} {r.get('mode')}; attempts {len(attempts)}; cost unknown")
    for candidate in r["candidates"]:
        for category in sorted({t["category"] for t in r["tasks"]}):
            rows = [a for a in attempts if a["candidate_id"] == candidate["id"] and a["category"] == category]
            if not rows: continue
            tokens = []
            for field in ("input_tokens", "output_tokens"):
                tokens.append("unknown" if any(a[field] is None for a in rows) else str(sum(a[field] for a in rows)))
            print(f"{candidate['id']} / {category}: passed {sum(a['passed'] for a in rows)}/{len(rows)}; "
                  f"median {median_latency(a['latency_ms'] for a in rows):.3f} ms; input/output tokens {tokens[0]}/{tokens[1]}")
def command_recommend(args): print(json.dumps(recommend(read_json(args.input),args.category,args.task),indent=2,allow_nan=False))
def command_export(args):
    r=validate_report(read_json(args.input))
    demo="DEMONSTRATION ONLY. " if r.get("mode")=="synthetic" else ""
    content=f"# {DISPLAY_NAME} guidance\n\n{demo}Microtask screening is provisional only. It is not validated full-programming routing. Guidance applies only to tested categories, tasks, and configurations. It grants no autonomous responsibility and makes no universal or provider-wide ranking. Native effort is selected only from the tested candidate configuration; no effort mapping occurs across providers.\n"
    content += (f"\nSource run: {r['run_id']}; mode: {r['mode']}; provenance: {r['provenance']['kind']}.\n"
                f"Suite version: {r['suite_version']}; SHA-256: {r['suite_hash']}.\n")
    if not demo:
        for category in sorted({t["category"] for t in r["tasks"]}):
            try:
                advice = recommend(r, category, "Follow the user's task requirements.")
                content += f"\n## {category}\n\nProvisional candidates: {', '.join(advice['shortlist'])}. Basis: {advice['selection_basis']}.\n"
                for evidence in advice["evidence"]:
                    if evidence["candidate_id"] in advice["shortlist"]:
                        content += "\nTested configuration: " + json.dumps(evidence["configuration"], sort_keys=True) + "\n"
                        content += (f"Evidence: {evidence['unique_tasks']} unique tasks, {evidence['attempts']} attempts; "
                                    f"quality {evidence['quality']:.3f}. Cost unknown.\n")
            except RecommendationError:
                content += f"\n## {category}\n\nInsufficient comparable evidence; no recommendation.\n"
    atomic_text(args.output,content,args.force); print(f"wrote {args.output}")
def parser():
    p=argparse.ArgumentParser(prog="model-captain",description=DISPLAY_NAME); sub=p.add_subparsers(dest="command",required=True)
    x=sub.add_parser("init"); x.add_argument("--config",default="model-guide.json"); x.set_defaults(fn=command_init)
    x=sub.add_parser("evaluate"); x.add_argument("--provider",choices=("demo","openai","anthropic","all"),default="demo"); x.add_argument("--config",default="model-guide.json"); x.add_argument("--suite"); x.add_argument("--output",required=True); x.add_argument("--repetitions",type=int,default=1); x.add_argument("--max-requests",type=int,default=12); x.add_argument("--live",action="store_true"); x.add_argument("--force",action="store_true"); x.set_defaults(fn=command_evaluate)
    for name,fn in (("report",command_report),("recommend",command_recommend),("export",command_export)):
      x=sub.add_parser(name); x.add_argument("--input",required=True); x.set_defaults(fn=fn)
      if name=="recommend": x.add_argument("--category",required=True); x.add_argument("--task",required=True)
      if name=="export": x.add_argument("--format",required=True,choices=("agents-md","claude-md")); x.add_argument("--output",required=True); x.add_argument("--force",action="store_true")
    return p
def main(argv=None):
    try: args=parser().parse_args(argv); args.fn(args); return 0
    except (ValidationError, StorageError, RecommendationError) as exc: print(f"error: {exc}",file=sys.stderr); return 2
    except KeyboardInterrupt: print("error: interrupted; no completed report written", file=sys.stderr); return 2
if __name__ == "__main__": raise SystemExit(main())
