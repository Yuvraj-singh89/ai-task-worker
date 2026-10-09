"""Independent verification: does NOT ask the LLM whether it worked. Reloads each claimed page from
the real system and checks that every expected string is actually there."""
def verify(browser, claims, wrote):
    if wrote and not claims:
        return False, "You changed system state but gave no claims. Re-open the affected page and finish with claims."
    problems = []
    for c in claims or []:
        try: page = browser.get(c["url"])
        except Exception as e: problems.append(f"{c.get('url')}: {e}"); continue
        if page["url"].split("?")[0].endswith("/login"):
            problems.append(f"{c['url']}: redirected to login (session lost) - log in again and re-check"); continue
        text = page["full_text"].lower()
        problems += [f"{c['url']}: expected '{e}' not found" for e in c.get("expect", []) if str(e).lower() not in text]
    return (not problems), ("; ".join(problems) or "all claims confirmed on the live system")
