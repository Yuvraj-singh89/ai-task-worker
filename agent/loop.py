"""The agent loop: Goal -> (LLM picks tool) -> policy gate -> execute -> observe -> ... -> verified finish."""
import json, re
from .tools import DATA, TOOL_DOC, needs_approval
from .verifier import verify

SYSTEM = """You are an autonomous AI operator employed by a company. Complete the user's task end-to-end using tools.
Reply with EXACTLY ONE JSON object per turn and nothing else: {"thought": "<short reasoning>", "tool": "<name>", "args": {...}}

""" + TOOL_DOC + """

RULES
- Use COMPANY CONTEXT for URLs, credentials and procedures. Do not ask the user for things you can find yourself.
- Work out the steps yourself. After every observation, decide the next action from what actually happened.
- If a page shows an error or a tool fails, read the message, fix the cause and retry differently. Never repeat an identical failing call.
- Sessions can expire: if you are sent to the login page, log in again and check whether your last action took effect.
- Use `remember` for key facts (source file, vendor, amount, due date) so they are not lost.
- Use ask_user ONLY when the task is genuinely ambiguous or impossible with available info (e.g. entity not found, several equal candidates).
- State-changing submissions are approved by a human automatically by the system; just attempt them. If denied, do not retry; report it.
- Success banners can lie. Before finishing a task that changed anything, re-open the affected page and finish with claims
  for the values that must be present. finish is rejected if the live system does not match your claims.
- Never invent data."""

def parse(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    try: d = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError: return None
    return d if isinstance(d, dict) and isinstance(d.get("tool"), str) else None

def run_agent(task, llm, tb, approve, trace, max_steps=25):
    ctx = (DATA / "company_context.md").read_text()
    msgs, recent = [{"role": "user", "content": f"TASK: {task}"}], []
    for step in range(1, max_steps + 1):
        system = f"{SYSTEM}\n\nCOMPANY CONTEXT:\n{ctx}\n\nWORKING MEMORY:\n{json.dumps(tb.memory, indent=1)}"
        raw = llm(system, msgs) or "(empty reply)"; trace(step, "llm", raw)
        msgs.append({"role": "assistant", "content": raw})
        act = parse(raw)
        if not act:
            obs = {"error": 'Invalid reply. Respond with one JSON object: {"thought":..., "tool":..., "args":{...}}'}
        else:
            tool, args = act["tool"], act.get("args") or {}
            trace(step, "action", {"tool": tool, "args": args})
            if tool == "finish":
                ok, msg = verify(tb.browser, args.get("claims"), tb.wrote); trace(step, "verification", {"ok": ok, "detail": msg})
                if ok: return {"status": "completed", "summary": args.get("summary", ""), "verification": msg, "steps": step}
                obs = {"error": f"VERIFICATION FAILED: {msg}. Fix the problem, then finish again."}
            else:
                reason = needs_approval(tool, args)
                if reason and not approve(reason):
                    obs = {"error": "DENIED by human reviewer. Do not retry; report this in your summary."}; trace(step, "approval", "denied")
                else:
                    if reason: trace(step, "approval", "granted")
                    obs = tb.call(tool, args)
            key = json.dumps([tool, args], sort_keys=True); recent = (recent + [key])[-3:]
            if len(recent) == 3 and len(set(recent)) == 1:
                obs["warning"] = "You repeated the same call 3 times. Change your approach or ask the user."
        trace(step, "observation", obs)
        msgs.append({"role": "user", "content": "OBSERVATION: " + json.dumps(obs)[:6000]})
    return {"status": "incomplete", "summary": f"Stopped after {max_steps} steps without a verified finish.", "steps": max_steps}
