"""Northwind Finance Portal - sandbox 'internal system' with deliberate failure modes:
  * session expires once after EXPIRE_AFTER authenticated requests (default 6, 0 = off)
  * due date must be YYYY-MM-DD, amount must be a plain number (422 + error message otherwise)
  * success banner is shown on redirect, so the agent must read data back to be sure.
Login: admin / admin123 (sandbox only)."""
import os, re
from datetime import datetime
from flask import Flask, request, session, redirect, render_template_string

app = Flask(__name__); app.secret_key = "sandbox-only"
INVOICES, ST = [], {"reqs": 0, "expired": False}

def reset():
    INVOICES[:] = [
        dict(id=1, vendor="Initech", amount="450.00", due="2026-10-12", status="OPEN"),
        dict(id=2, vendor="Globex Ltd", amount="2100.00", due="2026-10-05", status="OPEN")]
    ST.update(reqs=0, expired=False)
reset()

BASE = """<!doctype html><title>Northwind Finance Portal</title><h1>Northwind Finance Portal</h1>
{% if session.user %}<nav><a href="/invoices">Invoices</a> | <a href="/invoices/new">Add invoice</a></nav>{% endif %}
{% if msg %}<p class="msg">{{msg}}</p>{% endif %}BODY"""
LOGIN = '<h2>Login</h2><form method="post" action="/login">Username <input name="username"> Password <input name="password" type="password"><button>Log in</button></form>'
NEW = '''<h2>Add invoice</h2><form method="post" action="/invoices/new">
Vendor <input name="vendor" value="{{f.get('vendor','')}}"> Amount <input name="amount" value="{{f.get('amount','')}}">
Due date (YYYY-MM-DD) <input name="due_date" value="{{f.get('due_date','')}}"><button>Save invoice</button></form>'''
LIST = '''<h2>Invoices</h2><table><tr><th>ID</th><th>Vendor</th><th>Amount</th><th>Due date</th><th>Status</th><th></th></tr>
{% for i in inv %}<tr><td>{{i.id}}</td><td>{{i.vendor}}</td><td>{{i.amount}}</td><td>{{i.due}}</td><td>{{i.status}}</td>
<td>{% if i.status=='OPEN' %}<form method="post" action="/invoices/{{i.id}}/pay"><button>Mark paid</button></form>{% endif %}</td></tr>{% endfor %}</table>'''

def page(body, status=200, **kw):
    return render_template_string(BASE.replace("BODY", body), msg=request.args.get("msg"), **kw), status

@app.before_request
def guard():
    if request.path in ("/login", "/__reset"): return
    if not session.get("user"): return redirect("/login?msg=Please+log+in")
    n = int(os.environ.get("EXPIRE_AFTER", "6")); ST["reqs"] += 1
    if n and not ST["expired"] and ST["reqs"] > n:
        ST["expired"] = True; session.clear()
        return redirect("/login?msg=Session+expired.+Please+log+in+again.")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == "admin" and request.form.get("password") == "admin123":
            session["user"] = "admin"; return redirect("/invoices")
        return page(LOGIN, 401, msg="Invalid credentials")
    return page(LOGIN)

@app.route("/invoices")
def invoices(): return page(LIST, inv=INVOICES)

@app.route("/invoices/new", methods=["GET", "POST"])
def new():
    if request.method == "GET": return page(NEW, f={})
    f = request.form; err = None
    if not f.get("vendor", "").strip(): err = "Vendor is required."
    elif not re.fullmatch(r"\d+(\.\d{1,2})?", f.get("amount", "")): err = "Amount must be a plain number such as 1250.00 (no currency symbol or commas)."
    else:
        try: datetime.strptime(f.get("due_date", ""), "%Y-%m-%d")
        except ValueError: err = "Invalid due date. Use format YYYY-MM-DD."
    if err: return page(NEW, 422, f=f, msg="ERROR: " + err)
    INVOICES.append(dict(id=len(INVOICES) + 1, vendor=f["vendor"].strip(), amount=f["amount"], due=f["due_date"], status="OPEN"))
    return redirect("/invoices?msg=Invoice+saved+successfully")

@app.route("/invoices/<int:i>/pay", methods=["POST"])
def pay(i):
    for inv in INVOICES:
        if inv["id"] == i: inv["status"] = "PAID"; return redirect("/invoices?msg=Invoice+updated")
    return page("<p>Not found</p>", 404)

@app.route("/__reset", methods=["POST"])
def _reset(): reset(); return "ok"

if __name__ == "__main__": app.run(port=5000)
