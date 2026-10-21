#!/usr/bin/env python3
"""Check that every link and image URL in a Dyspatch email responds with HTTP 2xx.

Standard library only, so it runs in sandboxes and on the user's own machine.

Input: a JSON file holding a list of URLs, or a list of objects with a "url" key
(other keys such as "type", "blockIdx", "editableId" are passed through), or a
plain text file with one URL per line. URLs can also be given as arguments.

    python check_links.py --in links.json --out results.json --domains example.com
    python check_links.py https://example.com https://example.com/logo.png

Prints a JSON summary to stdout. Exit code is 0 even when links fail, so the
caller always gets the summary. A summary with "network_blocked": true means the
environment couldn't reach the web at all, and results shouldn't be reported as
broken links.
"""
import argparse
import json
import re
import socket
import ssl
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

UA = "Mozilla/5.0 (compatible; DyspatchEmailQA/1.0; +https://www.dyspatch.io)"
TEMPLATE_VAR = re.compile(r"@\{[^}]*\}|\{\{[^}]*\}\}|%%[^%]*%%|\*\|[^|]*\|\*")
# Dyspatch-hosted assets count as on-domain for every customer.
ALWAYS_OWNED = ("dyspatch.io",)


def load_items(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [{"url": line.strip()} for line in text.splitlines() if line.strip()]
    if isinstance(data, dict):
        # Accept a raw validate_template_revision response or {"links": [...]}.
        for key in ("templateLinks", "links", "urls"):
            if key in data:
                data = data[key]
                break
        else:
            found = find_key(data, "templateLinks")
            data = found if found is not None else []
    return [d if isinstance(d, dict) else {"url": d} for d in data]


def find_key(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        obj = list(obj.values())
    if isinstance(obj, list):
        for v in obj:
            r = find_key(v, key)
            if r is not None:
                return r
    return None


def owned(host, domains):
    host = (host or "").lower()
    for d in list(domains) + list(ALWAYS_OWNED):
        d = d.lower().lstrip("*.").strip()
        if d and (host == d or host.endswith("." + d)):
            return True
    return False


PLACEHOLDER_HOSTS = ("example.com", "example.org", "example.net", "domain.com", "yourdomain.com", "website.com")


def classify(url):
    """Return (result, reason) for a URL that shouldn't be fetched, else None.

    "placeholder" and "invalid" are problems to report; "skipped" means fine but not fetchable."""
    u = url.strip()
    if not u or u in ("#", "/"):
        return "placeholder", "empty_or_hash"
    if TEMPLATE_VAR.search(u):
        return "skipped", "contains_variable"
    parts = urlsplit(u)
    scheme = parts.scheme.lower()
    if scheme in ("mailto", "tel", "sms"):
        return "skipped", "non_http_scheme"
    if not scheme and not parts.netloc and (u.startswith("#") or u.startswith("?")):
        # "#download" or "?utm_source=x#download": an in-page anchor, which goes nowhere in an inbox.
        return "placeholder", "fragment_only"
    if scheme not in ("http", "https"):
        return "invalid", "no_scheme" if not scheme else "invalid_scheme"
    host = (parts.hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in PLACEHOLDER_HOSTS):
        return "placeholder", "placeholder_host"
    return None


def fetch(url, timeout):
    ctx = ssl.create_default_context()
    last = None
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return {"status": r.status, "final_url": r.geturl(), "content_type": r.headers.get("Content-Type", ""), "method": method}
        except urllib.error.HTTPError as e:
            last = {"status": e.code, "final_url": e.geturl() if hasattr(e, "geturl") else url, "method": method}
            # Many servers reject HEAD; retry those with GET.
            if method == "HEAD" and e.code in (400, 403, 404, 405, 429, 500, 501, 503):
                continue
            return last
        except (urllib.error.URLError, socket.timeout, ssl.SSLError, ConnectionError, OSError) as e:
            reason = getattr(e, "reason", e)
            last = {"status": None, "error": f"{type(e).__name__}: {reason}", "method": method}
            if method == "HEAD":
                continue
            return last
    return last


def check(item, domains, timeout):
    url = item["url"].strip()
    out = dict(item)
    host = urlsplit(url).hostname
    out["host"] = host
    out["on_domain"] = owned(host, domains) if host else None
    verdict = classify(url)
    if verdict:
        out["result"], out["reason"] = verdict
        return out
    r = fetch(url, timeout)
    out.update(r)
    status = r.get("status")
    if status and 200 <= status < 300:
        out["result"] = "ok"
        if r.get("final_url") and r["final_url"].rstrip("/") != url.rstrip("/"):
            out["redirected"] = True
    elif status:
        out["result"] = "http_error"
    else:
        out["result"] = "unreachable"
    if out.get("type", "").upper().startswith("IMAGE") and out["result"] == "ok":
        ct = (r.get("content_type") or "").lower()
        if ct and not ct.startswith("image/"):
            out["result"] = "not_an_image"
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--out")
    ap.add_argument("--domains", default="", help="comma-separated owned domains, e.g. example.com,example-cdn.net")
    ap.add_argument("--timeout", type=float, default=10)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    items = load_items(a.inp) if a.inp else []
    items += [{"url": u} for u in a.urls]
    seen, unique = set(), []
    for it in items:
        u = (it.get("url") or "").strip()
        if u not in seen:
            seen.add(u)
            unique.append(it)
    domains = [d for d in a.domains.split(",") if d.strip()]

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        results = list(ex.map(lambda it: check(it, domains, a.timeout), unique))

    fetched = [r for r in results if r["result"] not in ("skipped", "placeholder", "invalid")]
    unreachable = [r for r in fetched if r["result"] == "unreachable"]
    # If nothing at all could be reached, it's the sandbox, not the links.
    network_blocked = bool(fetched) and len(unreachable) == len(fetched)
    summary = {
        "checked": len(fetched),
        "ok": sum(r["result"] == "ok" for r in results),
        "placeholder": [{"url": r["url"], "reason": r["reason"]} for r in results if r["result"] == "placeholder"],
        "invalid": [{"url": r["url"], "reason": r["reason"]} for r in results if r["result"] == "invalid"],
        "http_error": [{"url": r["url"], "status": r["status"]} for r in results if r["result"] == "http_error"],
        "unreachable": [{"url": r["url"], "error": r.get("error")} for r in unreachable],
        "not_an_image": [r["url"] for r in results if r["result"] == "not_an_image"],
        "redirected": [{"url": r["url"], "final_url": r["final_url"]} for r in results if r.get("redirected")],
        "skipped": [{"url": r["url"], "reason": r["reason"]} for r in results if r["result"] == "skipped"],
        "off_domain": sorted({r["host"] for r in results if r.get("host") and r["on_domain"] is False}) if domains else None,
        "network_blocked": network_blocked,
    }
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "results": results}, f, indent=2)
    json.dump(summary, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
