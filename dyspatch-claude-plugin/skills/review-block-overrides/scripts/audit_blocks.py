#!/usr/bin/env python3
"""Audit Dyspatch blocks for hardcoded visual styles that override theme styles.

Inputs are the raw JSON responses of three Dyspatch MCP tools, saved to files:
  --blocks  GetAllBlocksQuery            (required: id, name, html per block)
  --usage   GetMinimalBlocksListQuery    (optional: templatesCount, themesCount)
  --themes  GetThemesWithBlockIDsQuery   (optional: active theme -> block IDs)

Output: a Markdown report (--out) and a one-line JSON summary on stdout.
Only the standard library is used, so it runs anywhere Python 3.8+ exists.
"""
import argparse, collections, datetime, html as H, json, re, sys

# Properties a theme controls. Spacing/size/alignment are excluded unless --include-spacing.
VISUAL_PROPS = (r"color|background(-color|-url|-image)?|container-background-color|inner-background-color|"
                r"border(-(top|right|bottom|left))?(-(color|width|style))?|border-radius|"
                r"font-(family|size|weight|style)|line-height|letter-spacing|text-(decoration|transform)")
SPACING_PROPS = r"padding(-(top|right|bottom|left))?|margin(-(top|right|bottom|left))?|inner-padding"

# Link to a block's code view in the Dyspatch app.
BLOCK_URL = "https://app.dyspatch.io/block/base/{id}/code"

# Values that don't lock a block to one theme: DML/theme variables and neutral keywords.
PORTABLE = re.compile(r"@\{|\{\{|^(transparent|inherit|initial|unset)$", re.I)

# Quote-aware tag matcher: attribute values may contain '>' (e.g. AMPscript <%...%>).
TAG = re.compile(r"<([a-zA-Z][\w-]*)((?:\s+[^\s=>/]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?)*)\s*/?>")
ATTR = re.compile(r"([\w-]+)\s*=\s*(['\"])(.*?)\2", re.S)


def load(path):
    """Load a saved MCP response. Handles both the bare JSON and the
    [{"type":"text","text":"<json>"}] content-block wrapper some clients save."""
    if not path:
        return None
    d = json.load(open(path, encoding="utf-8"))
    if isinstance(d, list) and d and isinstance(d[0], dict) and "text" in d[0]:
        d = json.loads(d[0]["text"])
    return d.get("data", d)


def category(prop):
    if "color" in prop or prop.startswith("background"):
        return "colour"
    if prop.startswith(("font", "line", "letter", "text")):
        return "typography"
    if prop.startswith(("padding", "margin", "inner-padding")):
        return "spacing"
    return "border"


def declarations(css):
    for d in css.split(";"):
        if ":" in d:
            p, v = d.split(":", 1)
            yield p.strip().lower(), v.strip()


def audit_html(src, is_flagged):
    """Return [(source, element_or_selector, property, value, important)]."""
    out = []
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    src = re.sub(r"<dys-comment>.*?</dys-comment>", "", src, flags=re.S)

    def add(source, where, prop, val):
        imp = "!important" in val
        val = val.replace("!important", "").strip()
        if val and is_flagged(prop) and not PORTABLE.search(val):
            out.append((source, where, prop, val, imp))

    # 1. <dys-style> CSS rules (innermost rule bodies, so media-query rules are caught too)
    for css in re.findall(r"<dys-style[^>]*>(.*?)</dys-style>", src, re.S):
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            for p, v in declarations(body):
                add("dys-style", " ".join(sel.split()), p, v)
    body = re.sub(r"<dys-style[^>]*>.*?</dys-style>", "", src, flags=re.S)

    # 2. Attributes on dys-* elements  3. inline style="" on any element
    for tag, attrs in TAG.findall(body):
        for k, _, v in ATTR.findall(attrs):
            k, v = k.lower(), H.unescape(v).strip()
            if k == "style":
                for p, sv in declarations(v):
                    add("inline style", tag, p, sv)
            elif tag.startswith("dys-"):
                add("attribute", tag, k, v)
    return out


def link(r):
    """Markdown link from block name to the block in the Dyspatch app."""
    return f"[{cell(r['name']).replace('[', '(').replace(']', ')')}]({BLOCK_URL.format(id=r['id'])})"


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--blocks", required=True)
    ap.add_argument("--usage")
    ap.add_argument("--themes")
    ap.add_argument("--out", default="block-override-report.md")
    ap.add_argument("--include-spacing", action="store_true", help="also flag padding/margin")
    a = ap.parse_args()

    pattern = VISUAL_PROPS + ("|" + SPACING_PROPS if a.include_spacing else "")
    flagged_prop = re.compile(rf"^({pattern})$").match

    blocks = load(a.blocks)["blocks"]["nodes"]
    usage = {b["id"]: b for b in (load(a.usage) or {"blocks": {"nodes": []}})["blocks"]["nodes"]}
    themes_data = load(a.themes)
    active_themes = collections.defaultdict(list)
    if themes_data:
        for t in themes_data["themes"]["nodes"]:
            for b in t["blocks"]["nodes"]:
                active_themes[b["id"]].append(t["name"])

    rows, colour_values = [], collections.Counter()
    for b in blocks:
        u = usage.get(b["id"], {})
        findings = audit_html(b.get("html") or "", flagged_prop)
        names = active_themes.get(b["id"], [])
        # themesCount (usage tool) includes archived themes; the themes tool lists active ones only.
        archived = max(u.get("themesCount", 0) - len(names), 0) if themes_data else 0
        notes = []
        if usage:
            if u.get("templatesCount", 0) == 0:
                notes.append("Not used in any template")
            if u.get("themesCount", 0) == 0:
                notes.append("Not assigned to any theme")
            elif themes_data and not names:
                notes.append("Only in archived themes")
        for f in findings:
            if category(f[2]) == "colour":
                colour_values[f[3].upper()] += 1
        rows.append(dict(id=b["id"], name=b["name"], themes=names, archived=archived,
                         templates=u.get("templatesCount", "?"), findings=findings, notes=notes))
    rows.sort(key=lambda r: (-len(r["findings"]), r["name"].lower()))

    flagged = [r for r in rows if r["findings"]]
    total = sum(len(r["findings"]) for r in rows)
    cats = ["colour", "typography", "border"] + (["spacing"] if a.include_spacing else [])
    arch = lambda r: f" (+{r['archived']} archived)" if r["archived"] else ""

    L = ["# Block theme-override review", "",
         f"- Date: {datetime.date.today().isoformat()}",
         f"- Blocks scanned: {len(rows)}",
         f"- Blocks with ≥1 hardcoded override: {len(flagged)}",
         f"- Clean blocks: {len(rows) - len(flagged)}",
         f"- Total overrides: {total}", "",
         f"**Flagged:** {', '.join(cats)} properties set to a fixed value.  ",
         "**Sources:** dys-* element attributes, inline `style=\"\"`, `<dys-style>` rules (`!important` marked).  ",
         "**Ignored:** theme/DML variables (`@{...}`), `transparent`/`inherit`, comments"
         + ("" if a.include_spacing else ", spacing/size/alignment") + ".", "",
         "## Summary", ""]
    if themes_data:
        L += ["Themes = active themes; archived theme assignments in brackets.", ""]
    L += ["| Block | Overrides | " + " | ".join(c.title() for c in cats) + " | !important | Themes | Templates | Note |",
          "|---|---|" + "---|" * len(cats) + "---|---|---|---|"]
    for r in rows:
        c = collections.Counter(category(f[2]) for f in r["findings"])
        L.append(f"| {link(r)} | {len(r['findings'])} | " + " | ".join(str(c[k]) for k in cats)
                 + f" | {sum(f[4] for f in r['findings'])} | {len(r['themes'])}{arch(r)} | {r['templates']} | {'; '.join(r['notes'])} |")
    L += ["", "## Most common hardcoded colour values", "", "| Value | Occurrences |", "|---|---|"]
    L += [f"| `{v}` | {n} |" for v, n in colour_values.most_common(15)]
    L += ["", "## Per-block detail", ""]
    for r in flagged:
        L += [f"### {r['name']}", "",
              f"{link(r)} · `{r['id']}` · Themes: {', '.join(r['themes']) or '—'}{arch(r)} · Templates: {r['templates']}"
              + (f" · **{'; '.join(r['notes'])}**" if r["notes"] else ""), "",
              "| Source | Element / selector | Property | Value |", "|---|---|---|---|"]
        L += [f"| {s} | `{cell(w)}` | {p} | `{cell(v)}`{' !important' if i else ''} |" for s, w, p, v, i in r["findings"]]
        L.append("")
    L += ["## Clean blocks", "", ", ".join(link(r) for r in sorted(rows, key=lambda r: r["name"].lower()) if not r["findings"]) or "—", ""]
    open(a.out, "w", encoding="utf-8").write("\n".join(L))

    notes = collections.Counter(n for r in rows for n in r["notes"])
    print(json.dumps(dict(report=a.out, blocks=len(rows), flagged=len(flagged), clean=len(rows) - len(flagged),
                          overrides=total, notes=notes,
                          top_blocks=[dict(name=r["name"], overrides=len(r["findings"]), url=BLOCK_URL.format(id=r["id"]))
                                      for r in flagged[:5]],
                          top_colours=colour_values.most_common(5))))


if __name__ == "__main__":
    sys.exit(main())
