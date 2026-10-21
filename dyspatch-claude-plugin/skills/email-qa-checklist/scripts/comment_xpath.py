#!/usr/bin/env python3
"""Compute the XPath that pins a Dyspatch comment (add_comment `coordinates`) to an element of an email.

Dyspatch comment coordinates are a JSON string:
    {"xpath":"/html/body[1]/div[1]/div[1]/div[1]/div[3]/div[1]/div[1]/table[1]/.../p[1]","x":0,"y":0}
The XPath is into the editor's preview DOM, which wraps every block of the email (hidden conditional blocks
included) in its own container:
    /html/body[1]/div[1]/div[1]/div[1]/div[<blockIdx, 1-based>]/div[1]/<path inside the block's HTML>
x/y are pixel offsets inside the element (0/0 is fine). If the XPath doesn't resolve, the app drops the pin in the
bottom-left of the email, so it has to be exact.

Input is per-block HTML from `render_template {input:{revisionId, showConditionalBlocks:true}}` (its `blockHtml`,
one fragment per block in order). Pass any of:
  - the raw saved response, or just the `blockHtml` array, or
  - a sparse file with only the blocks that need pins (cheapest to write by hand): {"blocks": {"3": "<div…>"}}.
    Each fragment can drop its <!--[if mso]> comments; nothing else may change.
Paths are built as a browser would (implicit <tbody>, auto-closed <p>/<td>), standard library only.

Usage:
    python comment_xpath.py blocks.json --block 3 --text "Lorem ipsum"  # element whose text contains this
    python comment_xpath.py blocks.json --block 3 --href "asdfasdf.com" # <a> whose href contains this
    python comment_xpath.py blocks.json --img "placeholder-logo"        # <img> whose src or alt contains this
    python comment_xpath.py blocks.json --block 3 --editable Button     # only if the HTML has data-visual-id
                                                                        # (render_unsaved_template output)
    python comment_xpath.py blocks.json --block 2                       # the whole block (no HTML needed)
    python comment_xpath.py blocks.json --batch targets.json
        # targets.json: [{"id":"L2","block":3,"href":"asdfasdfadsf"}, {"id":"C1","block":3,"text":"Lorem"}, {"id":"P1","block":2}]

Prints JSON with {"block", "xpath", "tag", "text", "coordinates"} per target; `coordinates` is the ready-to-send
string. A whole-block target, or one in a block whose render is empty, is pinned to the block's container.
Exit code 1 if any target wasn't found.
"""
import argparse
import json
import re
import sys
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
# Opening one of these closes an open <p> (HTML spec "close a p element").
CLOSES_P = {"address", "article", "aside", "blockquote", "div", "dl", "fieldset", "footer", "form", "h1", "h2", "h3",
            "h4", "h5", "h6", "header", "hr", "main", "nav", "ol", "p", "pre", "section", "table", "ul"}
# Preferred anchor tags for a text match: the smallest readable element.
TEXT_TAGS = ("a", "span", "strong", "em", "b", "i", "p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "div")


class Node:
    __slots__ = ("tag", "attrs", "parent", "children", "text")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.parent, self.children, self.text = tag, dict(attrs or {}), parent, [], []

    def append(self, child):
        child.parent = self
        self.children.append(child)
        return child

    def all_text(self):
        parts = list(self.text)
        for c in self.children:
            parts.append(c.all_text())
        return " ".join(p for p in parts if p)

    def xpath(self):
        steps, n = [], self
        while n.parent is not None:
            same = [c for c in n.parent.children if c.tag == n.tag]
            steps.append(f"{n.tag}[{same.index(n) + 1}]")
            n = n.parent
        steps.reverse()
        # The root step is written without an index, as the Dyspatch app does: /html/body[1]/…
        return "/" + "/".join([steps[0].split("[")[0]] + steps[1:]) if steps else "/"


class Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.doc = Node("#document")
        self.html = self.doc.append(Node("html"))
        self.head = self.html.append(Node("head"))
        self.body = None
        self.cur = self.head

    def _ensure_body(self):
        if self.body is None:
            self.body = self.html.append(Node("body"))
            self.cur = self.body

    def _open_ancestor(self, *tags):
        n = self.cur
        while n is not None and n.tag not in ("table", "body", "html"):
            if n.tag in tags:
                return n
            n = n.parent
        return n if n is not None and n.tag in tags else None

    def handle_starttag(self, tag, attrs):
        if tag == "html":
            self.html.attrs.update(dict(attrs))
            return
        if tag == "head":
            return
        if tag == "body":
            self._ensure_body()
            self.body.attrs.update(dict(attrs))
            return
        if self.body is None and tag not in ("title", "meta", "link", "style", "script", "base"):
            self._ensure_body()
        if tag in CLOSES_P:
            p = self._open_ancestor("p")
            if p is not None and p.tag == "p":
                self.cur = p.parent
        if tag in ("td", "th"):
            cell = self._open_ancestor("td", "th")
            if cell is not None and cell.tag in ("td", "th"):
                self.cur = cell.parent
        if tag == "tr":
            row = self._open_ancestor("tr")
            if row is not None and row.tag == "tr":
                self.cur = row.parent
            if self.cur.tag == "table":  # browsers wrap bare rows in an implicit tbody
                self.cur = self.cur.append(Node("tbody"))
        if tag in ("td", "th") and self.cur.tag in ("table", "tbody", "thead", "tfoot"):
            if self.cur.tag == "table":
                self.cur = self.cur.append(Node("tbody"))
            self.cur = self.cur.append(Node("tr"))
        node = self.cur.append(Node(tag, attrs))
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.cur.tag == tag:
            self.cur = self.cur.parent

    def handle_endtag(self, tag):
        if tag in ("html", "body", "head") or tag in VOID:
            if tag == "head" and self.cur is self.head:
                self.cur = self.html
            return
        n = self.cur
        while n is not None and n.tag != tag:
            if n.tag in ("table", "body", "html") and tag not in ("table",):
                return  # stray end tag: ignore, as browsers do
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        if data.strip():
            if self.body is None and self.cur is self.head:
                return
            self.cur.text.append(data.strip())


BLOCK_ROOT = "/html/body[1]/div[1]/div[1]/div[1]/div[{idx}]"
CONTAINER_X = 25


def load_blocks(path):
    """Return blockHtml as {blockIdx: html}: from a raw render response, a plain array, or a sparse
    {"blocks": {"3": "<html>", …}} holding only the blocks that need pins (cheapest to write by hand)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("blocks"), dict):
        return {int(k): v for k, v in data["blocks"].items()}
    stack = [data]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if isinstance(cur.get("blockHtml"), list):
                return dict(enumerate(cur["blockHtml"], 1))
            stack.extend(cur.values())
        elif isinstance(cur, list):
            if cur and all(isinstance(x, str) for x in cur):
                return dict(enumerate(cur, 1))
            stack.extend(cur)
    sys.exit("No block HTML found. Pass a render_template response, its blockHtml array, or {\"blocks\": {\"3\": \"…\"}}.")


def parse_block(fragment):
    b = Builder()
    b.feed(fragment)
    return b.body


def walk(n):
    yield n
    for c in n.children:
        yield from walk(c)


def norm(s):
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip().lower()


def find(body, target):
    nodes = list(walk(body))[1:]
    if "editable" in target:
        return [n for n in nodes if n.attrs.get("data-visual-id") == target["editable"]
                and not n.parent.attrs.get("data-visual-id") == target["editable"]]
    if "href" in target:
        return [n for n in nodes if n.tag == "a" and target["href"].lower() in n.attrs.get("href", "").lower()]
    if "img" in target:
        q = target["img"].lower()
        return [n for n in nodes if n.tag == "img" and (q in n.attrs.get("src", "").lower() or q in n.attrs.get("alt", "").lower())]
    q = norm(target["text"])
    hits = [n for n in nodes if n.tag in TEXT_TAGS and q in norm(n.all_text())]
    # keep the deepest matches: drop any hit that has another hit inside it
    hit_set = set(map(id, hits))
    return [h for h in hits if not any(id(d) in hit_set for d in walk(h) if d is not h)]


def coords(xp, x, y):
    return json.dumps({"xpath": xp, "x": x, "y": y}, separators=(",", ":"))


def describe(idx, n, x, y):
    # n.xpath() is /html/body[1]/<path in fragment>; the block's container replaces /html/body[1].
    xp = BLOCK_ROOT.format(idx=idx) + "/div[1]" + n.xpath()[len("/html/body[1]"):]
    label = (n.attrs.get("alt") or n.attrs.get("href") or n.all_text()).replace("\xa0", " ")
    return {"block": idx, "xpath": xp, "tag": n.tag, "text": label[:80], "coordinates": coords(xp, x, y)}


def resolve(blocks, target, x, y):
    """First match for one target, or a dict with xpath None."""
    has_selector = any(k in target for k in ("editable", "text", "href", "img"))
    if target.get("block") is not None:
        idx = int(target["block"])
        if idx not in blocks and has_selector:
            return {"block": idx, "xpath": None, "error": f"no HTML given for block {idx}"}
        order = [idx]
    else:
        order = sorted(blocks)
    for idx in order:
        frag = blocks.get(idx, "")
        if not has_selector or not frag.strip():
            if target.get("block") is None:
                continue  # an unscoped search skips hidden blocks
            # Whole block requested, or a block hidden by its condition: pin to the block's container.
            # A hidden block's container has no height, so the pin sits where the block would be, at the
            # email's left edge; nudge it in to line up with the usual 25px content padding.
            xp = BLOCK_ROOT.format(idx=idx)
            note = "hidden block (empty render), pinned to its container" if not frag.strip() else "whole block"
            return {"block": idx, "xpath": xp, "tag": "div", "text": note,
                    "coordinates": coords(xp, x or CONTAINER_X, y)}
        hits = find(parse_block(frag), target)
        if hits:
            return describe(idx, hits[0], x, y)
    return {"block": target.get("block"), "xpath": None, "error": "not found"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("render", help="render_unsaved_template response (JSON)")
    ap.add_argument("--block", type=int, help="1-based block index, as in validation blockIdx")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--editable", help="editable id, matched against data-visual-id")
    g.add_argument("--text")
    g.add_argument("--href")
    g.add_argument("--img")
    ap.add_argument("--batch", help="JSON list of targets: {id, block?, editable|text|href|img?}")
    ap.add_argument("--x", type=float, default=0)
    ap.add_argument("--y", type=float, default=0)
    a = ap.parse_args()

    blocks = load_blocks(a.render)
    if a.batch:
        with open(a.batch, encoding="utf-8") as f:
            targets = json.load(f)
    else:
        t = {k: v for k, v in (("block", a.block), ("editable", a.editable), ("text", a.text),
                               ("href", a.href), ("img", a.img)) if v is not None}
        if not t:
            ap.error("give --batch, or a target (--block and/or --editable/--text/--href/--img)")
        targets = [t]
    out = [{"id": t.get("id"), **resolve(blocks, t, a.x, a.y)} for t in targets]
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
    print()
    sys.exit(0 if all(o["xpath"] for o in out) else 1)


if __name__ == "__main__":
    main()
