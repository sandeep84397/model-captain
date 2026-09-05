import argparse, json, os, sys, time
from importlib.resources import files
from pathlib import Path
from . import DISPLAY_NAME
from .config import STARTER_CONFIG, load_config
from .evaluation import ValidationError, build_report, grade, validate_suite
from .recommendations import RecommendationError, recommend
from .providers import AnthropicProvider, OpenAIProvider, ProviderError, StdlibTransport
from .storage import StorageError, atomic_json, atomic_text, read_json

def bundled_suite(): return json.loads(files("model_guide.data").joinpath("programming.json").read_text())
def _demo_output(task): return json.dumps(task["expected"], separators=(",",":"))
def command_init(args): atomic_json(args.config, STARTER_CONFIG); print(f"wrote {args.config}")
def command_evaluate(args):
    suite=validate_suite(read_json(args.suite) if args.suite else bundled_suite()); config=load_config(read_json(args.config))
    candidates=[c for c in config["candidates"] if args.provider == "all" and c["provider"] != "demo" or c["provider"] == args.provider]
    if not candidates: raise ValidationError("no selected candidates")
    if type(args.repetitions) is not int or not 1<=args.repetitions<=10: raise ValidationError("repetitions must be 1..10")
    calls=len(suite["tasks"])*len(candidates)*args.repetitions
    if calls>args.max_requests or args.max_requests>1000: raise ValidationError("planned calls exceed max requests")
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
    attempts=[]
    for candidate in candidates:
      for task in suite["tasks"]:
       for rep in range(args.repetitions):
        started=time.monotonic()
        try:
            if candidate["provider"] == "demo": text=_demo_output(task); result=None
            else: result=providers[candidate["id"]].evaluate(candidate,task["prompt"],task); text=result.text
            attempts.append({"candidate_id":candidate["id"],"task_id":task["id"],"category":task.get("category"),"repetition":rep+1,"success":True,"passed":grade(text,task["grader"],task["expected"]),"latency_ms":round((time.monotonic()-started)*1000),"input_tokens":None if result is None else result.input_tokens,"output_tokens":None if result is None else result.output_tokens,"requested_model":candidate["model"],"returned_model":candidate["model"] if result is None else result.model,"cost":None})
        except ProviderError as exc:
            attempts.append({"candidate_id":candidate["id"],"task_id":task["id"],"category":task.get("category"),"repetition":rep+1,"success":False,"passed":False,"latency_ms":round((time.monotonic()-started)*1000),"input_tokens":None,"output_tokens":None,"requested_model":candidate["model"],"returned_model":None,"cost":None,"error":str(exc)})
    mode="synthetic" if not live_candidates else "live"; report=build_report(suite,candidates,args.repetitions,attempts,mode); atomic_json(args.output,report,args.force)
    print(f"{mode} complete: {calls} calls; cost unknown")
def command_report(args):
    r=read_json(args.input); attempts=r.get("attempts");
    if r.get("schema_version") != 1 or not isinstance(attempts,list): raise ValidationError("invalid report")
    print(f"run {r.get('run_id')} {r.get('completion_status')} {r.get('mode')}; attempts {len(attempts)}; cost unknown")
def command_recommend(args): print(json.dumps(recommend(read_json(args.input),args.category,args.task),indent=2))
def command_export(args):
    r=read_json(args.input)
    if r.get("schema_version") != 1 or not isinstance(r.get("attempts"),list): raise ValidationError("invalid report")
    demo="DEMONSTRATION ONLY. " if r.get("mode")=="synthetic" else ""
    content=f"# {DISPLAY_NAME} guidance\n\n{demo}Microtask screening is provisional only. It is not validated full-programming routing. Guidance applies only to tested categories, tasks, and configurations. It grants no autonomous responsibility and makes no universal or provider-wide ranking. Native effort is selected only from the tested candidate configuration; no effort mapping occurs across providers.\n"
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
if __name__ == "__main__": raise SystemExit(main())
