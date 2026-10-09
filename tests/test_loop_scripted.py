"""Offline test of everything EXCEPT the real LLM: a scripted 'model' drives the real loop, tools,
mock app, approval gate and verifier. Run: python tests/test_loop_scripted.py"""
import json, os, sys, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["EXPIRE_AFTER"] = "4"
from werkzeug.serving import make_server
from mock_app.app import app, INVOICES
from agent.loop import run_agent
from agent.tools import Browser, Toolbox

srv = make_server("127.0.0.1", 5055, app); threading.Thread(target=srv.serve_forever, daemon=True).start()
J = lambda tool, **args: json.dumps({"thought": "scripted", "tool": tool, "args": args})
good = {"url": "/invoices", "expect": ["Acme Corp", "1250.50", "2026-10-15"]}
script = iter([
    J("web_get", url="/login"),
    J("web_submit", action="/login", fields={"username": "admin", "password": "admin123"}),
    J("web_get", url="/invoices/new"),
    J("web_submit", action="/invoices/new", fields={"vendor": "Acme Corp", "amount": "$1,250.50", "due_date": "15 October 2026"}),  # 422
    J("web_submit", action="/invoices/new", fields={"vendor": "Acme Corp", "amount": "1250.50", "due_date": "2026-10-15"}),        # ok, then session expires
    J("web_submit", action="/login", fields={"username": "admin", "password": "admin123"}),
    J("finish", summary="done", claims=[{"url": "/invoices", "expect": ["9999.99"]}]),  # false claim -> must be rejected
    J("finish", summary="done", claims=[good]),
])
seen, approvals = [], []
res = run_agent("test", lambda s, m: next(script), Toolbox(Browser("http://127.0.0.1:5055"), input),
                lambda r: approvals.append(r) or True, lambda st, k, d: seen.append((k, d)))
kinds = [k for k, _ in seen]
assert res["status"] == "completed", res
assert len(approvals) == 2, approvals                       # both write attempts were gated, login was not
assert any(k == "verification" and not d["ok"] for k, d in seen)   # false claim was caught
assert any(i["vendor"] == "Acme Corp" and i["amount"] == "1250.50" for i in INVOICES)
print("PASS - steps:", res["steps"], "| approvals:", len(approvals), "| verification:", res["verification"])
