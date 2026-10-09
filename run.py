"""CLI:  python run.py "task text" [--provider anthropic|openai] [--model M] [--auto-approve]"""
import argparse, json, time
from pathlib import Path
from agent.llm import make_llm
from agent.loop import run_agent
from agent.tools import Browser, Toolbox

ap = argparse.ArgumentParser()
ap.add_argument("task"); ap.add_argument("--provider", default="anthropic", choices=["anthropic", "openai"])
ap.add_argument("--model"); ap.add_argument("--app-url", default="http://127.0.0.1:5000")
ap.add_argument("--auto-approve", action="store_true"); ap.add_argument("--max-steps", type=int, default=25)
a = ap.parse_args()

run_dir = Path("runs") / time.strftime("%Y%m%d-%H%M%S"); run_dir.mkdir(parents=True)
tfile = open(run_dir / "trace.jsonl", "w")
def trace(step, kind, data):
    tfile.write(json.dumps({"t": time.time(), "step": step, "kind": kind, "data": data}) + "\n"); tfile.flush()
    show = data if isinstance(data, str) else json.dumps(data)
    print(f"[{step:02d}] {kind:<12} {show[:230]}")

def ask(q): return input(f"\n  AGENT ASKS: {q}\n  > ")
def approve(what):
    if a.auto_approve: return True
    return input(f"\n  APPROVAL NEEDED: {what}\n  Approve? [y/N] ").strip().lower() == "y"

tb = Toolbox(Browser(a.app_url, run_dir / "pages"), ask)
res = run_agent(a.task, make_llm(a.provider, a.model), tb, approve, trace, a.max_steps)
(run_dir / "result.json").write_text(json.dumps({**res, "memory": tb.memory}, indent=2))
print(f"\n=== {res['status'].upper()} ===\n{res.get('summary')}\nVerification: {res.get('verification')}\nEvidence: {run_dir}/")
