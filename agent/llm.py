"""Thin LLM adapters over plain HTTP (no SDKs). llm(system, messages) -> text."""
import os, time, requests

_last_call = [0.0]
MIN_GAP = float(os.environ.get("LLM_MIN_GAP", "4"))   # seconds between calls (helps free-tier limits)

def _post(url, headers, body):
    for attempt in range(8):
        wait = MIN_GAP - (time.time() - _last_call[0])
        if wait > 0: time.sleep(wait)
        r = requests.post(url, headers=headers, json=body, timeout=120)
        _last_call[0] = time.time()
        if r.status_code in (429, 500, 502, 503, 529):
            delay = min(int(r.headers.get("Retry-After", 0)) or 10 * (attempt + 1), 60)
            print(f"  (API busy: {r.status_code}, waiting {delay}s, retry {attempt + 1}/8)")
            print("  REASON:", r.text[:500])
            time.sleep(delay); continue
        if r.status_code >= 400: print("API ERROR BODY:", r.text[:800])
        r.raise_for_status(); return r.json()
    r.raise_for_status()

def make_llm(provider, model=None):
    if provider == "anthropic":
        model = model or "claude-sonnet-5-5"
        def llm(system, messages):
            d = _post("https://api.anthropic.com/v1/messages",
                      {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
                      {"model": model, "max_tokens": 1024, "system": system, "messages": messages})
            return d["content"][0]["text"]
    else:  # any OpenAI-compatible endpoint (OpenAI, Gemini's /openai endpoint, Groq, Ollama...)
        model = model or "gpt-4o-mini"; base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        def llm(system, messages):
            d = _post(f"{base}/chat/completions", {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                      {"model": model, "messages": [{"role": "system", "content": system}] + messages})
            return d["choices"][0]["message"].get("content") or ""
    return llm
