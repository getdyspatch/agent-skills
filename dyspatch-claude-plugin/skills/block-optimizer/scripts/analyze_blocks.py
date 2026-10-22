#!/usr/bin/env python3
"""Analyze Dyspatch blocks and themes for optimization opportunities.

Inputs are raw Dyspatch MCP responses saved to files (bare JSON or the
[{"type":"text","text":…}] wrapper some clients save; several files per flag are fine):
  --blocks      get_blocks (one per theme, or one for the whole account)   required
  --themes      get_theme_with_blocks (one per theme in scope)              recommended
  --unassigned  get_unassigned_blocks                                       optional
  --usage       {"<blk_id>": <unix ts or ISO date of the newest template using it>, …}  optional
  --locale-groups get_locale_groups                                         optional
  --tags        get_tags {type:"block"}                                     optional

Phase 1 (no --usage / --heads): writes the report and prints `usage_candidates` (in-use blocks old
enough to be stale, to fetch get_block_templates for) and `head_renders` (one small block per theme, to
dry-run render and read the theme's Gmail light-mode lock from the <head>). Phase 2 (with --usage and
--heads): the report gains last-used dates, the stale list and the Gmail lock checks.

Outputs: findings JSON (--json), a Markdown report (--out) and a short JSON summary on stdout.
Standard library only (Python 3.8+).
"""
import argparse, collections, datetime, difflib, hashlib, html as H, itertools, json, re, sys
from urllib.parse import urlparse

BLOCK_URL = "https://app.dyspatch.io/block/base/{id}/code"
DYSPATCH_HOSTS = ("dyspatch.io",)  # cdn-web-assets.dyspatch.io, cdn-thumbnails.dyspatch.io, …
# Components editors use most; Variants / Mirror Layout should be switched on for these.
COMMON = ["dys-row", "dys-column", "dys-group", "dys-text", "dys-title", "dys-button", "dys-img"]
CONTENT_TAGS = ("dys-text", "dys-title", "dys-button", "dys-img", "dys-pill")
# Names that say nothing about the block. Plain layout names ("Text", "2 Column") are fine in a base library,
# so they're only flagged when another block in the same theme shares the name.
GENERIC_NAME = re.compile(r"^(copy of |duplicate of )|^(block|new block|untitled|test|group \d+|element \d+)( \d+)?$|\(copy\)$", re.I)
GENERIC_EDITABLE = re.compile(r"^(element \d+|true|editable|\d+|field \d+)$", re.I)
PLACEHOLDER_TEXT = re.compile(r"lorem ipsum|sed do eiusmod|button text|placeholder|your text here|"
                              r"headline goes here|text goes here", re.I)
BAD_LINK_TEXT = re.compile(r"^\s*(click here|here|read more|learn more|more|link|this)\s*$", re.I)
BAD_ALT = re.compile(r"^\s*(image|img|photo|picture|placeholder image|logo|banner|\S+\.(png|jpe?g|gif|webp))\s*$", re.I)
ESP_TRACKING = re.compile(r"/ls/click\?upn=|click\.[\w.-]+/|/track/click|mandrillapp\.com/track|"
                          r"list-manage\.com/track|ct\.sendgrid\.net|links\.[\w.-]+/(s|u)/|"
                          r"\.hubspotlinks\.com|cl\.exct\.net|click\.e\.[\w.-]+", re.I)
DARK_MODE = re.compile(r"prefers-color-scheme\s*:\s*dark|\[data-ogs[cb]\]", re.I)
# Old Gmail dark-mode workarounds (blend-mode hacks). Redundant once the theme's "Lock Light Mode in Gmail" is on.
GMAIL_HACK = re.compile(r"\.gmail-?(blend|screen|difference|dark)|mix-blend-mode", re.I)
ROOT_LIGHT_DARK = re.compile(r"color-scheme\s*:\s*light\s+dark", re.I)
TAG = re.compile(r"<(/?)([a-zA-Z][\w-]*)((?:\s+[^\s=>/]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?)*)\s*(/?)>")
ATTR = re.compile(r"([\w:-]+)\s*=\s*(['\"])(.*?)\2", re.S)
VAR = re.compile(r"@\{|\{\{|\{%|%%|<%")
RAW_HTML = re.compile(r"<(table|tr|td|div|span|center|font|style|script|iframe|form|input|label|video)\b", re.I)
BLOCK_COND = re.compile(r"<dys-(if|elif|else|if-else)\b")
REPEAT = re.compile(r"<dys-repeat\b", re.I)
INCLUDE = re.compile(r"<dys-include\b", re.I)


def load(path):
    d = json.load(open(path, encoding="utf-8"))
    if isinstance(d, list) and d and isinstance(d[0], dict) and "text" in d[0]:
        d = json.loads(d[0]["text"])
    return d.get("data", d) if isinstance(d, dict) else d


def ts(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def day(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date().isoformat() if t else "—"


PLACEHOLDER_DESC = re.compile(r"^\s*(test(ing)?|todo|tbd|tbc|desc(ription)?|lorem.*|asdf.*|xxx+|n/?a|none|block|new block|"
                              r"this is a (block|footer|header|test)\.?|auto import\b.*|not editable)\s*$", re.I)


def weak_description(b):
    """'missing', a reason string for a weak description, or None when it's fine."""
    d = (b.description or "").strip()
    if not d:
        return "missing"
    if PLACEHOLDER_DESC.match(d):
        return "is a placeholder or auto-generated note"
    if d.lower().rstrip(".") == b.name.strip().lower():
        return "just repeats the block name"
    if len(d) < 15:
        return "is too short to say what the block is for"
    return None


# Hints that tie a tag's name to what a block contains, so a tag that exists but isn't applied can be
# suggested for the right blocks. Tags whose names match none of these are left for the agent to judge.
TAG_HINTS = [
    (re.compile(r"logic|conditional|dynamic|personali[sz]", re.I), re.compile(r"<dys-(if|elif|for|repeat)\b", re.I), "uses conditionals or loops"),
    (re.compile(r"\bamp\b|interactive|kinetic", re.I), re.compile(r"<dys-(dynamic|form|carousel|list)\b|:checked", re.I), "has interactive or AMP content"),
    (re.compile(r"locali[sz]|translat|i18n|language", re.I), re.compile(r"\blocalizable=", re.I), "has localizable content"),
    (re.compile(r"promo|sale|offer|discount|coupon|deal", re.I), re.compile(r"promo|sale|offer|discount|coupon|% off|deal", re.I), "has promotional copy or a promo name"),
    (re.compile(r"footer|legal|compliance", re.I), re.compile(r"unsubscribe|privacy|©|&#169;|all rights reserved", re.I), "has footer or legal content"),
    (re.compile(r"header|logo|masthead", re.I), re.compile(r"DYS\.theme\.logo|\blogo\b", re.I), "has header or logo content"),
    (re.compile(r"\besp\b|ampscript|liquid|export", re.I), re.compile(r"<dys-export\b|<dys-raw\b", re.I), "has ESP-specific code"),
]


def tag_name(t, names):
    if isinstance(t, str):
        return names.get(t, t)
    if isinstance(t, dict):
        return t.get("name") or names.get(t.get("id"), t.get("id"))
    return str(t)


def strip_comments(src):
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    return re.sub(r"<dys-comment>.*?</dys-comment>", "", src, flags=re.S)


def elements(src):
    """Yield (tag, attrs dict, inner_text) for each opening tag. inner_text is the text up to the
    next tag (enough for button labels / short copy)."""
    for m in TAG.finditer(src):
        if m.group(1):
            continue
        attrs = {k.lower(): H.unescape(v) for k, _, v in ATTR.findall(m.group(3))}
        nxt = src.find("<", m.end())
        inner = H.unescape(src[m.end():nxt if nxt >= 0 else None]).strip() if not m.group(4) else ""
        yield m.group(2).lower(), attrs, inner


def host(u):
    try:
        return (urlparse(u).hostname or "").lower()
    except ValueError:
        return ""


def owned(h, domains):
    return any(h == d or h.endswith("." + d) for d in domains + list(DYSPATCH_HOSTS))


def normalize(src):
    s = strip_comments(src)
    s = re.sub(r"\s+editable=(['\"]).*?\1", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def structure(src):
    return " ".join(t for c, t, *_ in TAG.findall(strip_comments(src)) if t.startswith("dys-") and not c)


def luminance(hexc):
    hexc = hexc.lstrip("#")
    if len(hexc) == 3:
        hexc = "".join(c * 2 for c in hexc)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", hexc):
        return None
    rgb = [int(hexc[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    rgb = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    if la is None or lb is None:
        return None
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


class Block:
    def __init__(self, raw):
        self.id = raw["id"]
        self.name = raw.get("name") or self.id
        self.description = raw.get("description") or ""
        self.html = raw.get("html") or ""
        self.created = ts(raw.get("created"))
        self.modified = ts(raw.get("modified"))
        self.template_bound = bool(raw.get("isTemplateBound"))
        self.visual = bool(raw.get("isVisualBlock"))
        self.theme_ids = [t["id"] for t in raw.get("themes") or []]
        self.revision = raw.get("latestRevisionId")
        self.loc_schema = raw.get("localizationSchema") or []
        self.tags = raw.get("tags") or []
        self.editable_fields = raw.get("editableFields") or []
        self.templates = None   # from theme / unassigned payloads
        self.blueprints = None
        self.last_used = None
        self.findings = []

    def add(self, axis, severity, title, detail, fix="", auto=False):
        self.findings.append(dict(axis=axis, severity=severity, title=title, detail=detail, fix=fix, auto=auto))


def analyze_block(b, ctx):
    src = strip_comments(b.html)
    els = list(elements(src))
    tags = collections.Counter(t for t, *_ in els)
    content = [(t, a, i) for t, a, i in els if t in CONTENT_TAGS]
    editable = [(t, a, i) for t, a, i in content if "editable" in a]
    localizable = [(t, a, i) for t, a, i in els if "localizable" in a]
    b.stats = dict(content=len(content), editable=len(editable), localizable=len(localizable),
                   show=sum("show" in a for _, a, _ in els),
                   editable_styles=sum("editable-styles" in a for _, a, _ in els),
                   editable_group=sum(1 for f in b.editable_fields if f.get("editableGroup"))
                   + sum("editable-group" in a for _, a, _ in els),
                   conditionals=len(BLOCK_COND.findall(src)), repeat=len(REPEAT.findall(src)),
                   include=len(INCLUDE.findall(src)), raw=tags["dys-raw"] + tags["dys-html"],
                   table=tags["dys-table"], export=tags["dys-export"], style=tags["dys-style"],
                   theme_logo="DYS.theme.logo" in src, bytes=len(b.html))

    # --- Editability -------------------------------------------------------------------------
    locked = [(t, a, i) for t, a, i in content if "editable" not in a and "localizable" not in a
              and not VAR.search(i) and a.get("show") != "false"]
    if content and not editable and not localizable:
        fixed_ok = re.search(r"\b(footer|legal|disclaimer|header|logo|social|spacer|divider)\b", b.name, re.I)
        b.add("Editability", "Low" if fixed_ok else "Medium", "No editable elements",
              f"None of the {len(content)} content elements has `editable`, so every email gets identical copy and links."
              + (" That can be deliberate for a footer or header; check nothing in it changes per email." if fixed_ok
                 else " Editors can only add or remove the block."),
              "Add `editable='<clear id>'` to the copy, images and buttons that change per email.", True)
    elif locked:
        names = ", ".join(sorted({t for t, *_ in locked}))
        b.add("Editability", "Medium", f"{len(locked)} content element(s) not editable",
              f"Locked: {names}. Locked copy is right for legal text; wrong for headlines, CTAs and images.",
              "Make per-email content editable; leave legal/brand copy locked (or `localizable`).", True)
    generic = sorted({a["editable"] for _, a, _ in els if GENERIC_EDITABLE.match(a.get("editable", "-"))})
    if generic:
        b.add("Clarity", "Low", "Generic editable ids", f"Editors see field names like {', '.join(map(repr, generic[:5]))}.",
              "Rename editable ids to what the field is (`Headline`, `Hero image`, `Primary CTA`). Renaming breaks "
              "existing overrides in emails, so only do it on unused blocks or before rollout.", False)
    if editable and not b.stats["editable_styles"] and ctx["auto_editable_styles"] is False:
        b.add("Editability", "Low", "No editable-styles",
              "Editors can change copy but no styles, and the theme doesn't auto-enable editable styles.",
              "Add `editable-styles='…'` for the few properties editors legitimately change (alignment, padding, image width).")
    both = [a.get("editable") for _, a, _ in els if "editable" in a and "localizable" in a]
    if both:
        b.add("Editability", "High", "Element is both editable and localizable",
              f"{', '.join(map(repr, both[:3]))}: DML doesn't allow both on one element.",
              "Keep `editable` for per-email copy, or `localizable` for fixed translated copy.", True)
    dupe_ids = [k for k, n in collections.Counter(a["editable"] for _, a, _ in els if "editable" in a and "editable-group" not in a).items() if n > 1]
    if dupe_ids:
        b.add("Editability", "High", "Duplicate editable ids", f"{', '.join(map(repr, dupe_ids[:3]))} used more than once.",
              "Give each editable a unique id (or pair desktop/mobile copies with `editable-group`).")
    # dys-desktop / dys-mobile copies without an editable-group
    if tags["dys-mobile"] and tags["dys-desktop"] and editable and not b.stats["editable_group"]:
        b.add("Advanced features", "Medium", "Desktop and mobile copies edited separately",
              "The block has `dys-desktop` and `dys-mobile` versions with editable content but no `editable-group`, "
              "so editors must change the same copy twice and the versions drift.",
              "Give each desktop/mobile pair the same `editable-group` value so one control edits both.", True)
    elif (tags["dys-mobile"] or tags["dys-desktop"]) and not (tags["dys-mobile"] and tags["dys-desktop"]):
        b.add("Advanced features", "Low", "One-sided device targeting",
              f"Only `{'dys-mobile' if tags['dys-mobile'] else 'dys-desktop'}` is used, so the other device gets nothing.", "Add the counterpart, or drop the wrapper.")
    for t, a, _ in els:
        if t == "dys-repeat" and "editable" not in a:
            b.add("Advanced features", "High", "dys-repeat without editable", "`dys-repeat` needs an `editable` value to work.", "Add `editable='<id>'`.", True)
    # variants used in the block but not defined by its theme(s)
    defined = set().union(*[ctx["theme_variants"].get(i, set()) for i in b.theme_ids if i in ctx["theme_variants"]]) if any(i in ctx["theme_variants"] for i in b.theme_ids) else None
    if defined is not None:
        undefined = sorted({f"{t} '{a['variant']}'" for t, a, _ in els if a.get("variant") and not VAR.search(a["variant"]) and (t, a["variant"]) not in defined})
        if undefined:
            b.add("Theme features", "Medium", "Variant not defined in the theme",
                  f"{', '.join(undefined[:4])} isn't defined in the theme(s) analysed, so it renders with base styles.",
                  "Define the variant in the theme's `<dys-attributes>`, or switch to one that exists.")

    # --- Placeholder / clarity ----------------------------------------------------------------
    ph = [i[:40] for t, a, i in content if PLACEHOLDER_TEXT.search(i)]
    if ph and b.stats["editable"]:
        b.add("Clarity", "Low", "Sample copy as defaults",
              f"Default copy like {ph[0]!r} ships if an editor forgets to override it.",
              "Use realistic default copy or a short instruction editors can't miss; QA catches the rest.")

    # --- Links & images (one finding per kind per block, not per element) -----------------------
    hot, insecure, tracking, hard, hashes, noscheme = collections.defaultdict(int), [], [], [], 0, []
    # an <a> inside an editable text element is editable with it
    editable_text_spans = [(m.start(), m.end()) for m in re.finditer(
        r"<(dys-(?:text|title))\b[^>]*\b(?:editable|localizable)=[^>]*>.*?</\1>", src, re.S)]
    a_positions = iter(m.start() for m in TAG.finditer(src) if not m.group(1))
    for (t, a, i), pos in zip(els, a_positions):
        for attr in ("src", "background-url", "icon-src", "thumbnails-src"):
            u = a.get(attr, "")
            if u.startswith("http") and not VAR.search(u):
                h = host(u)
                if not owned(h, ctx["domains"]):
                    hot[h] += 1
                if u.startswith("http://"):
                    insecure.append(u)
        href = a.get("href", "")
        if not href or VAR.search(href):
            continue
        if ESP_TRACKING.search(href):
            tracking.append(href)
        elif href.startswith("http://"):
            insecure.append(href)
        elif re.match(r"(www\.|[\w-]+\.(com|net|org|io|co|ca|uk|de)\b)", href, re.I):
            noscheme.append(href)   # renders as a relative link, so it goes nowhere in an inbox
        locked = ("editable" not in a and "localizable" not in a and t in ("a", "dys-button", "dys-img", "dys-pill")
                  and not (t == "a" and any(s <= pos < e for s, e in editable_text_spans)))
        if locked and not href.startswith(("mailto:", "tel:", "#")):
            hard.append(href)
        if href == "#" and t in ("dys-button", "a", "dys-img"):
            hashes += 1
    if hot:
        b.add("Links & images", "Medium", "Hotlinked images",
              f"{sum(hot.values())} image(s) load from {', '.join(f'`{h}`' for h in sorted(hot))}, outside Dyspatch's asset library"
              + (" and your domains" if ctx["domains"] else "") + ". They can break, change or be blocked without notice.",
              "Upload them to the Dyspatch asset library (`upload_block_image_url`) and point the block at the hosted URLs.", True)
    if tracking:
        b.add("Links & images", "High", "ESP click-tracking URLs hardcoded",
              f"{len(tracking)} link(s) like `{tracking[0][:60]}…` are tracking redirects copied from a sent email. "
              "They report clicks to someone else's ESP account and eventually expire.", "Replace each with its destination URL.", True)
    if noscheme:
        b.add("Links & images", "High", "Links without https://",
              f"{len(noscheme)} link(s) like `{noscheme[0][:60]}` have no scheme, so email clients treat them as relative and they go nowhere.",
              "Add `https://` to each.", True)
    if insecure:
        b.add("Links & images", "Medium", "Insecure http:// URLs", f"{len(insecure)} URL(s), e.g. `{insecure[0][:70]}`.", "Use https.", True)
    if hard:
        b.add("Links & images", "Low", "Hardcoded links",
              f"{len(hard)} link(s) can't be changed per email, e.g. `{hard[0][:70]}`.",
              "Make per-email links editable; keep brand links (home, legal) locked or behind a variable.", True)
    if hashes:
        b.add("Links & images", "Low", "Placeholder `#` links", f"{hashes} link(s) default to `#`.", "Use a real default URL so a missed override isn't a dead link.")

    # --- Accessibility ------------------------------------------------------------------------
    imgs = [a for t, a, _ in els if t in ("dys-img", "dys-carousel-image") and a.get("show") != "false"]
    no_alt = [a for a in imgs if a.get("alt") is None]
    weak_alt = [a["alt"] for a in imgs if a.get("alt") is not None and BAD_ALT.match(a["alt"]) and "editable" not in a]
    if no_alt:
        b.add("Accessibility", "Medium", "Images without alt", f"{len(no_alt)} of {len(imgs)} image(s) have no `alt` attribute.",
              "Add descriptive alt (or `alt=''` if decorative); on editable images editors can then override it.", True)
    if weak_alt:
        b.add("Accessibility", "Low", "Weak alt text", f"Non-editable image(s) with alt {', '.join(map(repr, weak_alt[:3]))}.", "Describe the image.", True)
    for t, a, i in els:
        if t in ("a", "dys-button") and BAD_LINK_TEXT.match(i or "x"):
            b.add("Accessibility", "Low", "Vague link text", f"{t} text {i!r}.", "Say where the link goes.")
        fs = re.match(r"(\d+(?:\.\d+)?)px", a.get("font-size", ""))
        if fs and float(fs.group(1)) < 12 and t in ("dys-text", "dys-title", "dys-button", "a"):
            b.add("Accessibility", "Low", "Very small text", f"`{t}` font-size {fs.group(1)}px.", "Use 12px+ (14px+ for body).")
    # contrast between text colour and row/column background in this block
    bgs = [a["background-color"] for t, a, _ in els if t in ("dys-row", "dys-column", "dys-wrapper", "dys-section") and a.get("background-color", "").startswith("#")]
    for t, a, _ in els:
        c = a.get("color", "")
        if c.startswith("#") and bgs and t in ("dys-text", "dys-title", "dys-button", "a"):
            bg = a.get("background-color", bgs[-1]) if t == "dys-button" else bgs[-1]
            r = contrast(c, bg)
            if r and r < 4.5:
                b.add("Accessibility", "Medium" if r < 3 else "Low", "Low colour contrast",
                      f"`{t}` {c} on {bg} is {r:.1f}:1 (WCAG AA needs 4.5:1 for body text).", "Darken/lighten one colour, ideally via the theme.")
                break

    # --- Style consistency (overrides) ----------------------------------------------------------
    fixed = [(t, k, v) for t, a, _ in els for k, v in a.items()
             if t.startswith("dys-") and k in ("color", "background-color", "font-family", "font-size", "line-height", "font-weight")
             and v and not VAR.search(v) and v not in ("transparent", "inherit")]
    inline = sum(1 for _, a, _ in els if a.get("style"))
    if len(fixed) + inline >= 4:
        fams = sorted({v for t, k, v in fixed if k == "font-family"})
        b.add("Style consistency", "Medium" if len(fixed) + inline >= 10 else "Low", "Hardcoded styles",
              f"{len(fixed)} fixed colour/type attributes and {inline} inline `style`s override the theme"
              + (f"; fonts set in-block: {', '.join(fams[:3])}" if fams else "") + ". The block won't follow theme changes or work in another theme.",
              "Remove them so theme defaults apply, or move repeated looks into a theme variant. "
              "Run /dyspatch:review-block-overrides for the per-property list.")
    off_palette = sorted({v.upper() for t, k, v in fixed if "color" in k and v.startswith("#") and ctx["palette"] and v.upper() not in ctx["palette"]})
    if off_palette:
        b.add("Style consistency", "Low", "Colours outside the theme palette", ", ".join(off_palette[:6]), "Use palette colours or add them to the palette.")

    # --- Raw HTML -----------------------------------------------------------------------------
    raw_bits = re.findall(r"<dys-(raw|html)\b[^>]*>(.*?)</dys-\1>", src, re.S)
    stray = RAW_HTML.findall(re.sub(r"<dys-(raw|html|table|export)\b.*?</dys-\1>", "", src, flags=re.S))
    if raw_bits or stray or tags["dys-table"]:
        what = []
        if raw_bits:
            what.append(f"{len(raw_bits)} `dys-raw`/`dys-html` section(s)")
        if tags["dys-table"]:
            what.append(f"{tags['dys-table']} `dys-table`")
        if stray:
            what.append("raw tags " + ", ".join(sorted({s.lower() for s in stray})))
        snippet = re.sub(r"\s+", " ", raw_bits[0][1])[:160] if raw_bits else ""
        outside = len(re.findall(r"<dys-(?:raw|html)\b", re.sub(r"<dys-export\b.*?</dys-export>", "", src, flags=re.S)))
        b.add("Hardcoded HTML", "Medium", "Raw HTML in block",
              "; ".join(what) + (f"; {outside} raw section(s) outside `dys-export`, so they ship to every ESP" if outside else "")
              + (f". Starts: `{snippet}`" if snippet else "") + ". Raw HTML isn't editable, isn't themed, "
              "and skips DML's Outlook/mobile handling.",
              "Keep it only where DML can't express it (interactive CSS, ESP code wrapped in `dys-export`, schema markup), "
              "and say why in a `dys-comment`. Otherwise rebuild with dys-row/column/text/button.")
    html_comments = [c for c in re.findall(r"<!--(.*?)-->", b.html, re.S) if not re.match(r"\s*\[if|\s*<!\[endif", c)]
    if html_comments:
        b.add("Hardcoded HTML", "Low", "HTML comments ship to recipients",
              f"{len(html_comments)} `<!-- -->` comment(s) are exported into every email.", "Use `<dys-comment>`, which is stripped on export.", True)

    # --- Theme logo ---------------------------------------------------------------------------
    looks_header = re.search(r"\b(header|logo|masthead|nav)\b", b.name, re.I)
    first_img = next((a for t, a, _ in els if t == "dys-img"), None)
    if looks_header and first_img and "DYS.theme.logo" not in first_img.get("src", ""):
        b.add("Theme features", "Medium", "Logo not from the theme",
              f"Header/logo block hardcodes `{first_img.get('src', '')[:70]}`.",
              "Use `src='@{DYS.theme.logo.url}'` (and `href='@{DYS.theme.logo.href}'`) so one theme setting drives every email"
              + ("" if ctx["any_logo"] else "; set the logo on the theme first") + ".", True)

    # --- Dark mode in block ----------------------------------------------------------------------
    if tags["dys-social"] and any(a.get("theme") in ("black", "dark") for t, a, _ in els if t == "dys-social") and not ctx["theme_dark"]:
        b.add("Theme features", "Low", "Dark icons with no dark-mode handling",
              "`dys-social theme='black'` icons disappear on dark backgrounds, and the theme has no dark-mode rules.",
              "Add dark-mode CSS to the theme or use icons with a light outline.")

    # --- Localization ---------------------------------------------------------------------------
    static_text = [i for t, a, i in content if t in ("dys-text", "dys-title") and "editable" not in a and "localizable" not in a and len(i) > 20 and not VAR.search(i)]
    if ctx["localization"] and static_text and not b.stats["localizable"]:
        footerish = re.search(r"\b(footer|legal|disclaimer|address|unsubscribe|header|nav|social)\b", b.name, re.I)
        b.add("Localization", "Medium" if footerish else "Low", "Static copy not localizable",
              f"{len(static_text)} locked text element(s) (e.g. {static_text[0][:50]!r}) can't be translated, but the account localizes emails.",
              "Mark them `localizable='<key>'` and translate once at block level, so every email using the block gets the translations.", True)

    # --- Repetition → partials / dys-repeat -------------------------------------------------------
    # identical columns side by side → one partial included with id-suffix
    cols = re.findall(r"<dys-column\b[^>]*>(.*?)</dys-column>", src, re.S)
    sig = collections.Counter(structure(s) for s in cols if len(structure(s).split()) >= 2)
    rep = [(s, n) for s, n in sig.items() if n >= 2]
    if rep and not b.stats["include"]:
        s, n = rep[0]
        b.add("Advanced features", "Low", "Repeated columns — candidate for a partial",
              f"{n} columns repeat the same structure (`{s[:60]}`), so each copy is maintained by hand.",
              "Define it once as a `dys-partial` in `dys-includes` and place it with `<dys-include name='…' id-suffix='-1'/>`.")
    # 3+ consecutive rows/items with the same structure → list content editors should grow or shrink
    rows = [structure(r) for r in re.findall(r"<dys-row\b.*?</dys-row>", src, re.S)]
    items = [structure(x) for x in re.findall(r"<dys-(?:text|button|pill)\b[^>]*>.*?</dys-(?:text|button|pill)>", src, re.S)]
    run = max((len(list(g)) for k, g in itertools.groupby(rows) if k), default=0)
    count = run if run >= 3 else (len(items) if len(items) >= 4 and len(set(items)) == 1 and tags["dys-column"] <= 1 else 0)
    if count and not b.stats["repeat"]:
        b.add("Advanced features", "Medium", "List content — candidate for dys-repeat",
              f"{count} items repeat the same structure, so the block fixes how many there are.",
              "Wrap one item in `<dys-repeat editable='items'>` so editors add or remove items instead of needing 2-, 3- and 4-item blocks.")
    if b.stats["conditionals"]:
        b.add("Advanced features", "Info", "Uses in-block conditionals", f"{b.stats['conditionals']} `dys-if`/`dys-elif`/`dys-else` tags.", "")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--blocks", nargs="+", required=True)
    ap.add_argument("--themes", nargs="*", default=[])
    ap.add_argument("--unassigned")
    ap.add_argument("--usage")
    ap.add_argument("--locale-groups")
    ap.add_argument("--tags", help="get_tags {type:'block'} response")
    ap.add_argument("--heads", help='JSON {"thm_…": {"color_scheme_meta": "<content of <meta name=color-scheme> or \'\'>", '
                                    '"root_color_scheme": "<value of :root color-scheme or \'\'>"}} from one render per theme')
    ap.add_argument("--localization", choices=["yes", "no", "auto"], default="auto")
    ap.add_argument("--domains", default="", help="comma-separated owned domains (subdomains included)")
    ap.add_argument("--stale-days", type=int, default=365)
    ap.add_argument("--usage-max-templates", type=int, default=15,
                    help="only date blocks used by at most this many emails; busier blocks are assumed active")
    ap.add_argument("--scope", default="All blocks")
    ap.add_argument("--json", default="block-findings.json")
    ap.add_argument("--out", default="block-optimizer-report.md")
    a = ap.parse_args()
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    domains = [d.strip().lower().lstrip("*.") for d in a.domains.split(",") if d.strip()]

    blocks = {}
    for p in a.blocks:
        for raw in load(p)["blocks"]["nodes"]:
            blocks.setdefault(raw["id"], Block(raw))
    themes = []
    for p in a.themes:
        t = load(p)["theme"]
        themes.append(t)
        for n in t["blocks"]["nodes"]:
            if n["id"] in blocks:
                blocks[n["id"]].templates = n.get("templatesCount")
                blocks[n["id"]].blueprints = n.get("blueprintsCount")
    if a.unassigned:
        for n in load(a.unassigned)["unassignedBlocks"]["nodes"]:
            if n["id"] in blocks:
                blocks[n["id"]].templates = n.get("templatesCount")
                blocks[n["id"]].blueprints = n.get("blueprintsCount")
    usage = {}
    if a.usage:
        usage = {k: ts(v) for k, v in json.load(open(a.usage, encoding="utf-8")).items()}
        for k, v in usage.items():
            if k in blocks:
                blocks[k].last_used = v
    active_theme_ids = {t["id"] for t in themes}

    heads = json.load(open(a.heads, encoding="utf-8")) if a.heads else {}
    loc_groups = load(a.locale_groups).get("localeGroups", []) if a.locale_groups else []
    any_loc_block = any(b.loc_schema for b in blocks.values())
    localization = a.localization == "yes" or (a.localization == "auto" and (bool(loc_groups) or any_loc_block))

    # ---------------- Theme analysis ----------------
    theme_rows, theme_findings = [], []
    theme_variants = {}
    palette = set()
    theme_dark = False
    for t in themes:
        head = t.get("headContent") or ""
        try:
            esc = json.loads(t.get("editableStyleControls") or "{}")
        except ValueError:
            esc = {}
        defs = [(tg.lower(), H.unescape(v)) for tg, _, v in re.findall(r"<(dys-[\w-]+)[^>]*?\bvariant=(['\"])(.*?)\2", head)]
        theme_variants[t["id"]] = set(defs)
        variants = collections.Counter(tg for tg, _ in defs)
        var_on = [c for c in COMMON if esc.get(c, {}).get("variant")]
        mirror_on = [c for c in ("dys-row", "dys-group") if esc.get(c, {}).get("direction")]
        dark = bool(DARK_MODE.search(head))
        hack = bool(GMAIL_HACK.search(head))
        # "Lock Light Mode in Gmail" (Theme → Settings) isn't in the theme API; it shows only in the rendered <head>
        # as <meta name="color-scheme" content="light only">. None = not checked.
        h = heads.get(t["id"])
        gmail_lock = None if h is None else bool(re.search(r"\bonly\b", h.get("color_scheme_meta") or "", re.I))
        root_ld = bool(ROOT_LIGHT_DARK.search(head) or ROOT_LIGHT_DARK.search("color-scheme: " + ((h or {}).get("root_color_scheme") or "")))
        theme_dark = theme_dark or dark
        cols = (t.get("basicFields") or {}).get("colors", "")
        palette |= {c.strip().upper() for c in cols.split(",") if c.strip()}
        logo_set = bool(t.get("logoActive") and t.get("logoUrl"))
        uses_logo_var = [b for b in blocks.values() if t["id"] in b.theme_ids and "DYS.theme.logo" in b.html]
        row = dict(id=t["id"], name=t["name"], archived=t.get("archived"), blocks=len(t["blocks"]["nodes"]),
                   logo=logo_set, logo_blocks=len(uses_logo_var), variants=sum(variants.values()),
                   variant_components=sorted(variants), variants_enabled=var_on, mirror_enabled=mirror_on,
                   use_layouts=t.get("useLayouts"), auto_styles=t.get("autoEditableStyles"),
                   palette_only=t.get("usePaletteOnly"), dark_mode=dark, gmail_lock=gmail_lock, root_light_dark=root_ld,
                   fonts=re.findall(r"<dys-font[^>]*name=['\"]([^'\"]+)", head))
        theme_rows.append(row)

        def tf(sev, title, detail, fix, auto=False):
            theme_findings.append(dict(theme=t["name"], theme_id=t["id"], axis="Theme features", severity=sev,
                                       title=title, detail=detail, fix=fix, auto=auto))
        if not logo_set:
            tf("High", "No theme logo", "`logoUrl`/`logoActive` aren't set, so `@{DYS.theme.logo.url}` renders a placeholder.",
               "Set the theme logo (and its link) in theme settings, then point header blocks at `@{DYS.theme.logo.url}`.", True)
        elif not uses_logo_var:
            tf("Medium", "Theme logo set but unused", "No block in this theme uses `@{DYS.theme.logo…}`.",
               "Use the theme logo variable in the header block(s) so a logo change is one edit.", True)
        if not variants:
            tf("Medium", "No variants defined", "The theme defines no component variants (`variant=` in `<dys-attributes>`).",
               "Define named variants (e.g. Primary/Secondary button, Eyebrow text, Inverted row) so blocks pick a look instead of hardcoding it.")
        missing_var = [c for c in COMMON if c not in var_on]
        if missing_var:
            tf("Medium" if len(missing_var) > 3 else "Low", "Variants not enabled for common components",
               "Editors can't pick a variant on: " + ", ".join(missing_var) + ".",
               "Enable `variant` in the theme's editable style controls for these components.", True)
        if len(mirror_on) < 2:
            tf("Low", "Mirror Layout not fully enabled",
               "Mirror layout (`direction`) is " + ("only on " + ", ".join(mirror_on) if mirror_on else "off for dys-row and dys-group") + ".",
               "Enable `direction` for dys-row and dys-group so one Image|Content block also serves as Content|Image.", True)
        if not dark:
            tf("Medium", "No dark-mode targeting", "No `prefers-color-scheme: dark` (or Outlook `[data-ogsc]`) rules in the theme head.",
               "Add dark-mode CSS for backgrounds, text and logos (swap to a light logo), per Dyspatch's dark-mode guide.", True)
        verify = " Litmus/device previews of the Gmail app may still show forced dark mode; confirm with a real send to the Gmail app."
        if gmail_lock is False:
            tf("Medium" if not dark else "Low", "Lock Light Mode in Gmail is off",
               "The Gmail iOS/Android apps force-invert this theme's colours in dark mode"
               + (" and ignore its dark-mode styles." if dark else ", and the theme has no dark-mode styles of its own, so every dark-mode inbox is uncontrolled."),
               "If the brand should stay light in Gmail, turn on Theme → Settings → Lock Light Mode in Gmail (not settable via the MCP)."
               + (" Keep `:root { color-scheme: light dark; }` in the theme so Apple Mail still uses your dark styles." if dark else "")
               + verify)
        elif gmail_lock:
            if dark and not root_ld:
                tf("Medium", "Gmail lock hides your dark-mode styles elsewhere",
                   "Lock Light Mode in Gmail emits `color-scheme: light only`, which Apple Mail and other clients also obey, so the theme's "
                   "`prefers-color-scheme: dark` styles never apply.",
                   "Add `:root { color-scheme: light dark; }` in a `<dys-style>` in the theme head so other clients still use the dark styles." + verify, True)
            if hack:
                tf("Low", "Old Gmail dark-mode hack is redundant", "The theme head still has blend-mode/Gmail workaround CSS, but the Gmail lock is on.",
                   "Remove the workaround CSS after confirming with a real send.")
        if t.get("autoEditableStyles") is False:
            tf("Low", "Auto editable styles off", "Blocks only expose styles they list in `editable-styles`.", "Turn on auto editable styles, or audit blocks' editable-styles.")

    # variants the theme defines that no block in scope uses
    used_variants = {(t, a["variant"]) for b in blocks.values() for t, a, _ in elements(strip_comments(b.html)) if a.get("variant")}
    for t in themes:
        unused_v = sorted(f"{tg} '{v}'" for tg, v in theme_variants[t["id"]] - used_variants)
        if unused_v:
            theme_findings.append(dict(theme=t["name"], theme_id=t["id"], axis="Theme features", severity="Low",
                                       title="Variants no block uses", detail=", ".join(unused_v[:6]) + ". Editors may still pick them in the builder.",
                                       fix="Fine if editors choose them; otherwise remove stale variants (e.g. ones named after sample copy).", auto=False))
    ctx = dict(domains=domains, localization=localization, palette=palette, theme_dark=theme_dark, theme_variants=theme_variants,
               any_logo=any(r["logo"] for r in theme_rows),
               auto_editable_styles=(all(r["auto_styles"] for r in theme_rows) if theme_rows else None))

    # ---------------- Block analysis ----------------
    for b in blocks.values():
        analyze_block(b, ctx)

    # usage / inventory
    stale_cut = now - a.stale_days * 86400
    usage_candidates = []
    for b in blocks.values():
        in_active = [i for i in b.theme_ids if i in active_theme_ids]
        if not b.theme_ids:
            b.add("Inventory", "Medium", "Not in any theme", "Editors can't add it to new emails.", "Assign it to a theme or retire it.")
        if b.template_bound:
            b.add("Inventory", "Info", "Template-bound (one-off) block", "Belongs to a single email.", "")
        if b.templates == 0 and not b.blueprints:
            b.add("Inventory", "High" if b.created and b.created < stale_cut else "Medium", "Unused block",
                  "No email, draft or blueprint uses it" + (f" (created {day(b.created)})" if b.created else "") + ".",
                  "Remove it from the theme (keeps it recoverable) or delete it after confirming.")
        elif b.templates:
            if b.last_used is not None:
                if b.last_used < stale_cut:
                    b.add("Inventory", "Medium", f"Not used in {a.stale_days}+ days",
                          f"Used by {b.templates} email(s), but none edited since {day(b.last_used)}.",
                          "Consider retiring it or merging it into a current block.")
            elif not (b.created and b.created > stale_cut):
                usage_candidates.append(b)
    # get_block_templates returns every email using the block (~0.3 KB each), so a block in 90 emails costs ~30 KB.
    # Heavily used blocks are almost never stale: date only the lightly used ones, least used first.
    usage_candidates.sort(key=lambda b: b.templates)
    usage_skipped = [dict(id=b.id, name=b.name, templates=b.templates) for b in usage_candidates if b.templates > a.usage_max_templates]
    usage_candidates = [b.id for b in usage_candidates if b.templates <= a.usage_max_templates]
    a.usage_skipped = usage_skipped

    # duplicates
    groups = collections.defaultdict(list)
    for b in blocks.values():
        if b.html.strip():
            groups[hashlib.sha1(normalize(b.html).encode()).hexdigest()].append(b)
    dup_groups = [g for g in groups.values() if len(g) > 1]
    seen = {id(b) for g in dup_groups for b in g}
    near = []
    lib = [b for b in blocks.values() if id(b) not in seen and b.html.strip() and not b.template_bound]
    by_struct = collections.defaultdict(list)
    for b in lib:
        by_struct[structure(b.html)].append(b)
    for sig, g in by_struct.items():
        if len(g) < 2 or len(sig.split()) < 3:
            continue
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                r = difflib.SequenceMatcher(None, normalize(g[i].html), normalize(g[j].html)).ratio()
                if r >= 0.85:
                    near.append((g[i], g[j], r))
    for g in dup_groups:
        keep = max(g, key=lambda x: (x.templates or 0, -(x.created or 0)))
        for b in g:
            if b is not keep:
                b.add("Duplicates", "High", "Exact duplicate",
                      f"Same DML as [{keep.name}]({BLOCK_URL.format(id=keep.id)}) (used by {keep.templates if keep.templates is not None else '?'} emails).",
                      "Replace uses with the kept block, then retire this one.")
    for x, y, r in near:
        x.add("Duplicates", "Medium", "Near-duplicate",
              f"{r:.0%} similar to [{y.name}]({BLOCK_URL.format(id=y.id)}), same structure.",
              "Merge into one block: expose the differences with `show`, editable styles, a variant or a conditional.")
    names = collections.Counter((b.name.strip().lower(), tuple(sorted(b.theme_ids))) for b in blocks.values())
    for b in blocks.values():
        if names[(b.name.strip().lower(), tuple(sorted(b.theme_ids)))] > 1 and not any(f["axis"] == "Duplicates" for f in b.findings):
            b.add("Clarity", "Low", "Name shared with another block in the same theme(s)", f"'{b.name}'.", "Give each block a distinct, descriptive name.")
        if GENERIC_NAME.search(b.name.strip()):
            b.add("Clarity", "Low", "Unhelpful block name", f"'{b.name}' doesn't tell an editor what it's for.",
                  "Name by purpose and layout, e.g. 'Hero — image left, CTA'.")
        if not b.template_bound:
            why = weak_description(b)
            if why:
                busy = (b.templates or 0) >= 10
                b.add("Clarity", "Medium" if busy else "Low", "No description" if why == "missing" else "Weak description",
                      ("No description" if why == "missing" else f"Description {b.description.strip()[:60]!r} {why}")
                      + (f", and it's used in {b.templates} emails" if b.templates else "")
                      + ". Editors see the description in the block picker; it's how they tell similar blocks apart.",
                      "Write one sentence on what the block is for and when to use it (e.g. 'Hero with image left and one CTA; use for launches').", True)

    # ---------------- Tags ----------------
    tag_defs = []
    if a.tags:
        tag_defs = [t for t in ((load(a.tags).get("tags") or {}).get("data") or [])
                    if t.get("isActive", True) and "block" in (t.get("type") or ["block"])]
    id2name = {t["id"]: t["name"] for t in tag_defs}
    for b in blocks.values():
        b.tag_names = sorted({tag_name(t, id2name) for t in b.tags})
    lib_b = [b for b in blocks.values() if not b.template_bound]
    all_tags = sorted({t["name"] for t in tag_defs} | {n for b in lib_b for n in b.tag_names})
    near_of = collections.defaultdict(set)
    for x, y, _ in near:
        near_of[x.id].add(y.id), near_of[y.id].add(x.id)
    for g in dup_groups:
        for b in g:
            near_of[b.id] |= {o.id for o in g if o is not b}
    tag_rows = []
    for tg in all_tags:
        members = [b for b in lib_b if tg in b.tag_names]
        hint = next((h for h in TAG_HINTS if h[0].search(tg)), None)
        member_tokens = collections.Counter(w for m in members for w in set(re.findall(r"[a-z]{4,}", m.name.lower())))
        shared = {w for w, n in member_tokens.items() if n >= 2}
        sugg = []
        for b in lib_b:
            if tg in b.tag_names:
                continue
            reason = None
            if any(o in near_of[b.id] for o in (m.id for m in members)):
                reason = "is a near-duplicate of a block tagged with it"
            elif hint and hint[1].search(" ".join((b.name, b.description, b.html))):
                reason = hint[2]
            elif shared & set(re.findall(r"[a-z]{4,}", b.name.lower())):
                reason = "is named like the blocks tagged with it"
            if reason:
                sugg.append((b, reason))
        tag_rows.append(dict(tag=tg, tagged=len(members), suggested=len(sugg), hinted=bool(hint or members)))
        for b, reason in sugg[:25]:
            b.add("Tags", "Low", f"Possibly missing tag '{tg}'", f"Not tagged '{tg}', but it {reason}.",
                  f"Add the '{tg}' tag if it fits, so editors can filter for it in the block picker.", True)
    tagged_count = sum(1 for b in lib_b if b.tag_names)
    tag_summary = dict(defined=[t["name"] for t in tag_defs], blocks_tagged=tagged_count, library=len(lib_b),
                       unmatched=[r["tag"] for r in tag_rows if not r["hinted"]], rows=tag_rows)

    # account-level feature adoption
    all_b = list(blocks.values())
    adoption = dict(
        blocks=len(all_b),
        editable=sum(1 for b in all_b if b.stats["editable"]),
        editable_styles=sum(1 for b in all_b if b.stats["editable_styles"]),
        editable_group=sum(1 for b in all_b if b.stats["editable_group"]),
        show=sum(1 for b in all_b if b.stats["show"]),
        conditionals=sum(1 for b in all_b if b.stats["conditionals"]),
        repeat=sum(1 for b in all_b if b.stats["repeat"]),
        include=sum(1 for b in all_b if b.stats["include"]),
        localizable=sum(1 for b in all_b if b.stats["localizable"]),
        theme_logo=sum(1 for b in all_b if b.stats["theme_logo"]),
        raw_html=sum(1 for b in all_b if b.stats["raw"] or b.stats["table"]),
        export=sum(1 for b in all_b if b.stats["export"]),
    )
    # partial candidates: identical rows shared by 3+ blocks
    row_owner = collections.defaultdict(set)
    for b in all_b:
        for r in re.findall(r"<dys-row\b.*?</dys-row>", strip_comments(b.html), re.S):
            n = normalize(r)
            if len(n) > 200:
                row_owner[hashlib.sha1(n.encode()).hexdigest()].add(b.id)
    shared_rows = sorted((ids for ids in row_owner.values() if len(ids) >= 3), key=len, reverse=True)
    if shared_rows and not adoption["include"]:
        for ids in shared_rows[:3]:
            for bid in ids:
                blocks[bid].add("Advanced features", "Medium", "Shared section — candidate for a partial",
                                f"The same row appears in {len(ids)} blocks: " + ", ".join(blocks[i].name for i in list(ids)[:4]) + ".",
                                "Move it into a partial/include so a change is made once.")

    # ---------------- Score & output ----------------
    rows = sorted(all_b, key=lambda b: (-sum(SEV[f["severity"]] for f in b.findings), b.name.lower()))
    number(rows, theme_findings)
    findings = [dict(block=b.name, block_id=b.id, url=BLOCK_URL.format(id=b.id), templates=b.templates, **f)
                for b in rows for f in b.findings] + theme_findings
    json.dump(dict(scope=a.scope, date=datetime.date.today().isoformat(), themes=theme_rows, adoption=adoption,
                   localization_in_use=localization, tags=tag_summary, findings=findings,
                   blocks=[dict(id=b.id, name=b.name, templates=b.templates, blueprints=b.blueprints, last_used=day(b.last_used) if b.last_used else None,
                                created=day(b.created), modified=day(b.modified), themes=b.theme_ids, stats=b.stats) for b in rows]),
              open(a.json, "w", encoding="utf-8"), indent=1)
    write_report(a, rows, theme_rows, theme_findings, adoption, localization, dup_groups, near, findings, tag_summary)

    by_axis = collections.Counter(f["axis"] for f in findings if f["severity"] != "Info")
    by_sev = collections.Counter(f["severity"] for f in findings if f["severity"] != "Info")
    unused = [b for b in all_b if b.templates == 0 and not b.blueprints]
    # For themes whose Gmail lock wasn't checked: the smallest block in the theme, to dry-run render its <head>.
    head_renders = {}
    for r in theme_rows:
        if r["gmail_lock"] is None:
            cands = [b for b in all_b if r["id"] in b.theme_ids and b.revision and b.html.strip()]
            if cands:
                s = min(cands, key=lambda b: len(b.html))
                head_renders[r["id"]] = dict(blockId=s.id, blockRevisionId=s.revision)
    print(json.dumps(dict(report=a.out, findings_json=a.json, blocks=len(all_b), themes=len(themes),
                          severity=by_sev, by_axis=by_axis, unused=len(unused), exact_duplicate_groups=len(dup_groups),
                          near_duplicates=len(near), usage_unknown=sum(1 for b in all_b if b.templates is None),
                          localization_in_use=localization, usage_candidates=usage_candidates,
                          usage_candidate_templates=sum(blocks[i].templates for i in usage_candidates),
                          usage_skipped=len(a.usage_skipped), head_renders=head_renders,
                          tags=dict(defined=tag_summary["defined"], blocks_tagged=tag_summary["blocks_tagged"],
                                    unmatched=tag_summary["unmatched"], suggested={r["tag"]: r["suggested"] for r in tag_summary["rows"]}),
                          top=[dict(name=b.name, id=b.id, score=sum(SEV[f["severity"]] for f in b.findings),
                                    issues=[f["title"] for f in b.findings if f["severity"] in ("High", "Medium")][:4])
                               for b in rows[:8]])))


SEV = {"High": 3, "Medium": 2, "Low": 1, "Info": 0}
PREFIX = {"Inventory": "I", "Duplicates": "D", "Editability": "E", "Clarity": "C", "Accessibility": "A",
          "Style consistency": "S", "Links & images": "L", "Hardcoded HTML": "H", "Theme features": "T",
          "Advanced features": "F", "Localization": "Z", "Tags": "G"}


def number(rows, theme_findings):
    """Give every finding a stable reference (TH1 for themes, L2, E3… for blocks) so the user can say 'fix L2'.
    Findings are sorted most severe first within each block."""
    theme_findings.sort(key=lambda f: -SEV[f["severity"]])
    for i, f in enumerate(theme_findings, 1):
        f["ref"] = f"TH{i}"
    num = collections.Counter()
    for b in rows:
        b.findings.sort(key=lambda f: -SEV[f["severity"]])
        for f in b.findings:
            if f["severity"] == "Info":
                continue
            p = PREFIX.get(f["axis"], "X")
            num[p] += 1
            f["ref"] = f"{p}{num[p]}"


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def link(name, bid):
    return f"[{cell(name).replace('[', '(').replace(']', ')')}]({BLOCK_URL.format(id=bid)})"


def write_report(a, rows, theme_rows, theme_findings, adoption, localization, dup_groups, near, findings, tags):
    n = adoption["blocks"] or 1
    pct = lambda k: f"{adoption[k]} ({adoption[k] * 100 // n}%)"
    sev = collections.Counter(f["severity"] for f in findings if f["severity"] != "Info")
    L = ["# Block optimization report", "",
         f"{a.scope} · {datetime.date.today().isoformat()} · {adoption['blocks']} blocks · {len(theme_rows)} themes · stale after {a.stale_days} days", "",
         f"**{sev['High']} High · {sev['Medium']} Medium · {sev['Low']} Low**", "",
         "## Summary", "", "<!-- SUMMARY: the agent replaces this line with 3–6 bullets -->", ""]
    if theme_rows:
        yes = lambda v: "Yes" if v else "**No**"
        L += ["## Themes", "", "| Theme | Blocks | Logo set | Blocks using theme logo | Variants defined | Variants enabled on | Mirror layout | Dark mode | Gmail light lock |",
              "|---|---|---|---|---|---|---|---|---|"]
        for r in theme_rows:
            L.append(f"| {cell(r['name'])} (`{r['id']}`) | {r['blocks']} | {yes(r['logo'])} | {r['logo_blocks']} | "
                     f"{r['variants'] or '**0**'} | {', '.join(c.replace('dys-', '') for c in r['variants_enabled']) or '**none**'} | "
                     f"{', '.join(c.replace('dys-', '') for c in r['mirror_enabled']) or '**off**'} | {yes(r['dark_mode'])} | {'?' if r['gmail_lock'] is None else 'On' if r['gmail_lock'] else 'Off'} |")
        L += ["", "| # | Theme | Severity | Finding | Detail | Suggested fix |", "|---|---|---|---|---|---|"]
        for f in theme_findings:
            L.append(f"| {f['ref']} | {cell(f['theme'])} | {f['severity']} | {cell(f['title'])} | {cell(f['detail'])} | {cell(f['fix'])} |")
        L.append("")
    L += ["## Feature adoption", "", "| Feature | Blocks using it |", "|---|---|",
          f"| `editable` content | {pct('editable')} |", f"| `editable-styles` | {pct('editable_styles')} |",
          f"| editable groups | {pct('editable_group')} |", f"| `show` (optional elements) | {pct('show')} |",
          f"| in-block conditionals (`dys-if`) | {pct('conditionals')} |", f"| `dys-repeat` | {pct('repeat')} |",
          f"| partials / includes | {pct('include')} |", f"| `localizable` | {pct('localizable')} |",
          f"| theme logo variable | {pct('theme_logo')} |", f"| `dys-export` (ESP-specific code) | {pct('export')} |",
          f"| raw HTML / `dys-table` | {pct('raw_html')} |", "",
          f"Localization in use in the account: **{'yes' if localization else 'no'}**.", ""]
    lib = [b for b in rows if not b.template_bound]
    no_desc = sum(1 for b in lib if not (b.description or "").strip())
    weak = sum(1 for b in lib if (b.description or "").strip() and weak_description(b))
    L += ["## Descriptions and tags", "",
          f"- Blocks with no description: **{no_desc}** of {len(lib)} · weak descriptions (placeholder, too short, repeats the name): **{weak}**"]
    if not a.tags:
        L.append("- Tags: not checked (get_tags wasn't fetched)")
    elif not tags["rows"]:
        L.append("- Tags: no block tags are defined in the account. Worth setting up if editors struggle to find blocks "
                 "(e.g. 'Hero', 'Footer', 'Promo', 'Has logic').")
    else:
        L.append(f"- Block tags defined: {', '.join(tags['defined']) or '—'} · blocks tagged: **{tags['blocks_tagged']}** of {tags['library']}"
                 + (" (tags exist but no block uses them)" if not tags["blocks_tagged"] else ""))
        L += ["", "| Tag | Blocks tagged | Suggested additions |", "|---|---|---|"]
        L += [f"| {cell(r['tag'])} | {r['tagged']} | {r['suggested'] if r['hinted'] else '— (needs your judgement)'} |" for r in tags["rows"]]
    L.append("")
    unused = [b for b in rows if b.templates == 0 and not b.blueprints]
    stale = [b for b in rows if any(f["title"].startswith("Not used in") for f in b.findings)]
    L += ["## Inventory", "", f"- Unused (no emails, drafts or blueprints): **{len(unused)}**",
          f"- Not used in {a.stale_days}+ days: **{len(stale)}**" + ("" if a.usage else " (last-use dates not fetched)"),
          f"- Not dated (used in more than {a.usage_max_templates} emails, so assumed active): **{len(a.usage_skipped)}**",
          f"- Exact-duplicate groups: **{len(dup_groups)}** · near-duplicate pairs: **{len(near)}**",
          f"- Not in any theme: **{sum(1 for b in rows if not b.theme_ids)}**", ""]
    if unused:
        L += ["| Unused block | Created | Last modified |", "|---|---|---|"]
        L += [f"| {link(b.name, b.id)} | {day(b.created)} | {day(b.modified)} |" for b in sorted(unused, key=lambda b: b.created or 0)]
        L.append("")
    if stale:
        L += ["| Stale block | Emails | Last email edit |", "|---|---|---|"]
        L += [f"| {link(b.name, b.id)} | {b.templates} | {day(b.last_used)} |" for b in stale]
        L.append("")
    if dup_groups or near:
        L += ["### Duplicates", ""]
        for g in dup_groups:
            L.append("- **Identical:** " + ", ".join(f"{link(b.name, b.id)} ({b.templates if b.templates is not None else '?'} emails)" for b in g))
        for x, y, r in near:
            L.append(f"- **{r:.0%} similar:** {link(x.name, x.id)} ↔ {link(y.name, y.id)}")
        L.append("")
    L += ["## Blocks", "", "| Block | Emails | High | Medium | Low | Top issues |", "|---|---|---|---|---|---|"]
    for b in rows:
        c = collections.Counter(f["severity"] for f in b.findings)
        top = "; ".join(dict.fromkeys(f["title"] for f in b.findings if f["severity"] in ("High", "Medium")))[:140]
        L.append(f"| {link(b.name, b.id)} | {b.templates if b.templates is not None else '?'} | {c['High']} | {c['Medium']} | {c['Low']} | {cell(top) or '—'} |")
    L += ["", "## Findings by block", ""]
    for b in rows:
        fs = [f for f in b.findings if f["severity"] != "Info"]
        if not fs:
            continue
        L += [f"### {cell(b.name)}", "", f"{link('Open in Dyspatch', b.id)} · `{b.id}` · emails: {b.templates if b.templates is not None else '?'} · created {day(b.created)} · modified {day(b.modified)}", "",
              "| # | Axis | Severity | Finding | Detail | Suggested fix |", "|---|---|---|---|---|---|"]
        for f in fs:
            L.append(f"| {f['ref']} | {f['axis']} | {f['severity']} | {cell(f['title'])} | {cell(f['detail'])} | {cell(f['fix'])} |")
        L.append("")
    L += ["## Not checked", "", "<!-- NOT CHECKED: the agent lists anything skipped, and why -->", ""]
    open(a.out, "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
