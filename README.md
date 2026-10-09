# Autonomous AI Task Worker (CentrAlign AI – AI Engineering Intern assignment)

A small agent that takes a natural-language task, works out the steps itself, operates a (sandbox) company web
app and local files, recovers from failures, asks for approval before writing, and **verifies the result against
the live system** before it is allowed to say "done".

Demo video: https://drive.google.com/file/d/1BWQ0vSx5JZOYMQJuBp6b2o-3zznfBHsO/view?usp=sharing · Author: Yuvraj Singh

## Quick start
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...            # or: OPENAI_API_KEY=... (+ OPENAI_BASE_URL for Gemini/Groq/Ollama)

python mock_app/app.py                  # terminal 1: the sandbox "internal system" (http://127.0.0.1:5000)

# terminal 2
python run.py "Find the latest invoice from Acme Corp, extract the amount and due date, enter it into the internal invoice system, and tell me once it is done."

# other tasks - SAME code, nothing changed:
python run.py "Mark the Globex Ltd invoice as paid."
python run.py "Which invoices in the system are due before 2026-10-13? Summarise."
python run.py "Enter the latest invoice from Hooli."          # entity doesn't exist -> agent should ask / report
# Gemini:  OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai OPENAI_API_KEY=<key> python run.py "..." --provider openai --model gemini-2.5-flash
# Reset portal data between runs: restart the mock app.   Offline test (no API key): python tests/test_loop_scripted.py
```
Every run writes `runs/<timestamp>/`: `trace.jsonl` (every thought / action / observation / approval / verification),
`pages/*.html` (snapshot of every page the agent saw) and `result.json` (summary + memory) = the evidence.

## Architecture
```
 task ─► LLM (decides next tool) ─► policy gate (needs_approval) ─► Toolbox ─► observation ─┐
            ▲  system prompt = rules + COMPANY CONTEXT + WORKING MEMORY                     │
            └───────────────────────────────────────────────────────────────────────────────┘
 finish(summary, claims) ─► verifier reloads pages from the live system ─► accept / reject (rejection goes back to LLM)
```
| File | Role |
|---|---|
| `agent/loop.py` | The loop. ~60 lines, no framework. One JSON action per turn, errors fed back as observations, repeat-call detection, step cap |
| `agent/tools.py` | `list_files, read_file, web_get, web_submit, remember, ask_user, finish`; session-based browser limited to the allowed host; file access sandboxed to `data/`; approval policy |
| `agent/verifier.py` | Independent read-back check of the agent's claims – no LLM involved |
| `agent/llm.py` | Provider adapters (Anthropic, any OpenAI-compatible API) over plain HTTP |
| `mock_app/app.py` | Flask finance portal with injected failures |
| `data/company_context.md` | "Company memory": URLs, credentials (sandbox), procedures, definitions |

## Key design decisions (and why)
1. **Hand-written loop, no LangChain/agent framework.** The control flow is the product; I wanted to be able to explain and modify every line.
2. **Nothing task-specific in code.** Invoices appear only in data (company context, sample files, mock app). The loop/tools/verifier know nothing about invoices, so new tasks need no code change – the model reads the page's forms/links and decides.
3. **Verification is code, not opinion.** `finish` needs `claims` (url + expected strings). The verifier re-fetches those pages and rejects the finish if reality doesn't match. If anything was written, finishing without claims is rejected too. The portal shows a success banner even when it isn't proof, so read-back matters.
4. **Safety lives outside the prompt.** The approval gate is enforced in code for every state-changing POST (login exempt); the model cannot skip it. Denial is returned as an observation and the agent must report it.
5. **Failures are observations.** Tool errors, HTTP 422 validation messages and login redirects go back to the model, which adapts (e.g. `$1,250.50` → `1250.50`, `15 October 2026` → `2026-10-15`, re-login after expiry).
6. **State = working memory + history.** `remember` facts are re-injected into the system prompt every turn, so they survive long histories.
7. **HTTP browser instead of Playwright.** Forms/links are parsed from HTML, which gives the model a compact, reliable view. It keeps the prototype dependency-light and deterministic; the `Browser` class is the seam where a Playwright/computer-use backend would plug in.

## Failure modes built into the sandbox (to demonstrate reliability)
- Amount rejected if it has `$` or commas; due date rejected unless `YYYY-MM-DD` (HTTP 422 + message).
- Session expires once after 6 authenticated requests – typically *right after* a write, so the agent must re-login and check the write really happened (`EXPIRE_AFTER=0` disables, set the env var before starting the app).
- Invoice filenames are meaningless (`scan_00N.txt`), amounts include line items, dates come in 3 formats, 3 Acme invoices exist (latest = by invoice date).

## Testing
`tests/test_loop_scripted.py` runs the real loop, tools, app, approval gate and verifier with a scripted stand-in for the model. It checks: validation failure → retry, session expiry mid-write → re-login, both writes gated, a **false claim is rejected by the verifier**, and a correct claim is accepted. I also ran live-model runs: “Live runs with gemini-3.5-flash-lite: the Acme task completed and verified, including recovery from session expiry and an empty model reply; the Globex ‘mark paid’ task completed and verified with the same code.”.

## Models / services / components
Claude (`claude-sonnet-5-5`) or any OpenAI-compatible model via plain HTTP · Flask (mock app) · requests + BeautifulSoup · pypdf (optional). Written with AI coding assistance; I can explain and modify every part.

## Assumptions
Sandbox credentials are in the company-context file; "latest" = most recent invoice date; one user, one portal; invoice files are text/text-PDF; the human at the terminal is the approver.

## Known limitations
- Only server-rendered HTML sites; no JavaScript-heavy pages, no screenshots / vision / desktop control.
- Verification checks strings on a page – it can be weak if the claims are weak (e.g. only a vendor name). A stricter version would diff the table row.
- No OCR for scanned PDFs; text is truncated to 3.5–6k chars per observation.
- Memory is per-run (no persistence across runs); single sequential agent; no cost/token budget; model JSON-format errors are only handled by a re-prompt.
- Approval is a blunt "every write" rule, not a per-risk policy.

## What I'd build next
1. Playwright + screenshot/vision backend behind the same `Browser` interface; DOM-diffing to detect "nothing happened".
2. Structured claims (typed row-level checks) and a second, cheaper "auditor" pass.
3. Persistent company memory (procedures learned from feedback) and per-task resumable state.
4. An eval harness: 20+ tasks × injected faults, tracking success / steps / unsafe-action rate.
5. Granular permissions (read vs. write vs. irreversible), audit log export, and cost/step budgets.
