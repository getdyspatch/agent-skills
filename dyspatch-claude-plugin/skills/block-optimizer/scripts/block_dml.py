#!/usr/bin/env python3
"""Print the DML of a few blocks from saved get_blocks responses, without loading the whole file into context.

    python block_dml.py blocks-*.json --ids blk_a,blk_b [--max-chars 4000] [--meta]

--meta adds isTemplateBound / isVisualBlock / latestRevisionId / themes (needed for update_block).
Long tracking URLs are shortened so they don't eat the output. Standard library only.
"""
import argparse, json, re, sys


def load(path):
    d = json.load(open(path, encoding="utf-8"))
    if isinstance(d, list) and d and isinstance(d[0], dict) and "text" in d[0]:
        d = json.loads(d[0]["text"])
    return d.get("data", d)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--ids", required=True)
    ap.add_argument("--max-chars", type=int, default=4000)
    ap.add_argument("--meta", action="store_true")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    want = [i.strip() for i in a.ids.split(",") if i.strip()]
    found = {}
    for f in a.files:
        for b in load(f)["blocks"]["nodes"]:
            if b["id"] in want:
                found.setdefault(b["id"], b)
    for i in want:
        b = found.get(i)
        if not b:
            print(f"===== {i}: not found")
            continue
        src = re.sub(r"(https?://[^\s'\"]{60})[^\s'\"]+", r"\1…", b.get("html") or "")
        print(f"===== {b['name']} ({i}) · {len(b.get('html') or '')} chars")
        if a.meta:
            meta = {k: b.get(k) for k in ("isTemplateBound", "isVisualBlock", "latestRevisionId", "description")}
            print(json.dumps(dict(meta, themes=[t["id"] for t in b.get("themes") or []])))
        print(src[:a.max_chars] + ("\n…[truncated]" if len(src) > a.max_chars else ""))


if __name__ == "__main__":
    main()
