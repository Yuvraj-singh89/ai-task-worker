"""Tools the agent can use. Every tool returns a JSON-able dict; errors are returned (never raised)
so the loop can feed them back to the model as observations."""
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

DATA = Path(__file__).resolve().parent.parent / "data"

TOOL_DOC = """TOOLS (call exactly one per turn):
- list_files {"path": "."}                      list files under the company data folder
- read_file {"path": "invoices/x.txt"}          read a text/PDF file from the data folder
- web_get {"url": "/invoices"}                  open a page of the internal system; returns text, forms (action/method/fields) and links
- web_submit {"action": "/login", "fields": {"name": "value"}, "method": "POST"}   submit a form (POSTs other than login need human approval)
- remember {"key": "vendor", "value": "..."}    store a fact in working memory (shown to you every turn)
- ask_user {"question": "..."}                  ask the human for clarification
- finish {"summary": "...", "claims": [{"url": "/invoices", "expect": ["Acme Corp", "1250.50"]}]}
     end the task. Each claim is independently re-checked by loading the url and looking for every expected string."""

class Browser:
    """Session-based web client (cookies kept). Restricted to the configured host."""
    def __init__(self, base_url, snap_dir=None):
        self.base, self.s, self.snap_dir, self.n = base_url.rstrip("/"), requests.Session(), snap_dir, 0
        if snap_dir: Path(snap_dir).mkdir(parents=True, exist_ok=True)

    def _url(self, u):
        full = urljoin(self.base + "/", u)
        if urlparse(full).netloc != urlparse(self.base).netloc:
            raise ValueError(f"Blocked: {full} is outside the allowed host")
        return full

    def _render(self, r):
        self.n += 1
        if self.snap_dir: (Path(self.snap_dir) / f"page_{self.n:02d}.html").write_text(r.text)
        soup = BeautifulSoup(r.text, "html.parser")
        forms = [{"action": f.get("action") or urlparse(r.url).path, "method": f.get("method", "get").upper(),
                  "fields": [{"name": i["name"], "value": i.get("value", "")} for i in f.find_all(["input", "select", "textarea"]) if i.get("name")]}
                 for f in soup.find_all("form")]
        links = [{"text": a.get_text(strip=True), "href": a["href"]} for a in soup.find_all("a", href=True)]
        for f in soup.find_all("form"): f.decompose()
        for tr in soup.find_all("tr"):
            tr.replace_with(soup.new_string(" | ".join(c.get_text(strip=True) for c in tr.find_all(["td", "th"])) + "\n"))
        p = urlparse(r.url)
        return {"status": r.status_code, "url": p.path + (f"?{p.query}" if p.query else ""),
                "full_text": soup.get_text("\n", strip=True), "forms": forms, "links": links}

    def get(self, url): return self._render(self.s.get(self._url(url), timeout=10))
    def submit(self, action, fields, method="POST"):
        u = self._url(action)
        return self._render(self.s.post(u, data=fields, timeout=10) if method.upper() == "POST" else self.s.get(u, params=fields, timeout=10))

class Toolbox:
    def __init__(self, browser, ask):
        self.browser, self.ask, self.memory, self.wrote = browser, ask, {}, False

    def _safe(self, p):
        full = (DATA / p).resolve()
        if DATA.resolve() not in [full, *full.parents]: raise ValueError("Path outside data folder")
        return full

    def _page(self, p):  # what the model sees
        return {**{k: v for k, v in p.items() if k != "full_text"}, "text": p["full_text"][:3500]}

    def list_files(self, path="."):
        return {"files": sorted(str(f.relative_to(DATA)) for f in self._safe(path).rglob("*") if f.is_file())}

    def read_file(self, path):
        f = self._safe(path)
        if f.suffix.lower() == ".pdf":
            from pypdf import PdfReader
            return {"content": "\n".join(pg.extract_text() or "" for pg in PdfReader(f).pages)[:6000]}
        return {"content": f.read_text(errors="replace")[:6000]}

    def web_get(self, url): return self._page(self.browser.get(url))

    def web_submit(self, action, fields, method="POST"):
        p = self.browser.submit(action, fields, method)
        if method.upper() == "POST" and "login" not in action and p["status"] < 400: self.wrote = True
        return self._page(p)

    def remember(self, key, value): self.memory[key] = value; return {"ok": True}
    def ask_user(self, question): return {"answer": self.ask(question)}

    def call(self, name, args):
        if name not in ("list_files", "read_file", "web_get", "web_submit", "remember", "ask_user"):
            return {"error": f"Unknown tool '{name}'"}
        try: return getattr(self, name)(**args)
        except Exception as e: return {"error": f"{type(e).__name__}: {e}"}

def needs_approval(tool, args):
    """Policy lives in code, not in the prompt: any state-changing POST (except login) needs a human yes."""
    if tool == "web_submit" and str(args.get("method", "POST")).upper() == "POST" and "login" not in str(args.get("action", "")):
        return f"POST {args.get('action')} with {args.get('fields')}"
