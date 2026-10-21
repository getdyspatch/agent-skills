#!/usr/bin/env python3
"""Convert the Markdown QA report to a styled HTML page or a Word document.

    python render_report.py qa-report.md --format html   # -> qa-report.html
    python render_report.py qa-report.md --format docx   # -> qa-report.docx
    python render_report.py qa-report.md --format docx --out "C:/reports/Spring QA.docx"

Handles the Markdown the skill writes: headings, paragraphs, bullet and numbered lists, pipe tables,
**bold**, *italic*, `code` and [links](url). Severity words (Blocker, Warning, FYI) and the verdict are
colour-coded in both formats. Standard library only (no pandoc or python-docx needed). The .docx is
landscape so the findings tables fit. Prints the output path.
"""
import argparse
import html
import re
import zipfile
from pathlib import Path

SEVERITY = {"blocker": "#C62828", "warning": "#B26A00", "fyi": "#1565C0",
            "not ready": "#C62828", "ready after fixes": "#B26A00", "ready": "#2E7D32",
            "pass": "#2E7D32", "fail": "#C62828"}
INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\)|https?://[^\s<>()|]*[^\s<>()|.,;:!?'\"]"
                    r"|(?<!\*)\*[^*\s][^*]*\*(?!\*))")


# ---------- Markdown parsing (just what the report uses) ----------

def parse(md):
    """Return a list of blocks: (kind, data). kinds: h, p, ul, ol, table, hr, code."""
    lines = md.replace("\r\n", "\n").split("\n")
    blocks, i = [], 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue
        if s.startswith("```"):
            buf, i = [], i + 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            blocks.append(("code", "\n".join(buf)))
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            blocks.append(("h", (len(m.group(1)), m.group(2).strip())))
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):
            blocks.append(("hr", None))
            i += 1
            continue
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-{2,}", lines[i + 1].strip()):
            rows = [split_row(s)]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i].strip()))
                i += 1
            blocks.append(("table", rows))
            continue
        if re.match(r"^[-*+]\s+", s) or re.match(r"^\d+[.)]\s+", s):
            ordered = bool(re.match(r"^\d+[.)]\s+", s))
            items = []
            while i < len(lines) and lines[i].strip():
                t = lines[i]
                mm = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", t)
                if mm:
                    items.append((len(mm.group(1).expandtabs(2)) // 2, mm.group(3)))
                elif items:
                    items[-1] = (items[-1][0], items[-1][1] + " " + t.strip())
                i += 1
            blocks.append(("ol" if ordered else "ul", items))
            continue
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,6}\s|\||[-*+]\s|\d+[.)]\s|```)", lines[i].strip()):
            buf.append(lines[i].strip())
            i += 1
        blocks.append(("p", " ".join(buf)))
    return blocks


def split_row(s):
    s = s.strip().strip("|")
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", s)]


def inline_tokens(text):
    """Yield (kind, text, href) with kind in plain/bold/italic/code/link."""
    pos = 0
    for m in INLINE.finditer(text):
        if m.start() > pos:
            yield ("plain", text[pos:m.start()], None)
        t = m.group(0)
        if t.startswith("**"):
            yield ("bold", t[2:-2], None)
        elif t.startswith("`"):
            yield ("code", t[1:-1], None)
        elif t.startswith("["):
            lm = re.match(r"\[([^\]]+)\]\(([^)\s]+)\)", t)
            yield ("link", lm.group(1), lm.group(2))
        elif t.startswith("http"):
            yield ("link", t, t)
        else:
            yield ("italic", t[1:-1], None)
        pos = m.end()
    if pos < len(text):
        yield ("plain", text[pos:], None)


def severity_of(text):
    t = re.sub(r"[*`]", "", text).strip().lower()
    return SEVERITY.get(t)


# ---------- HTML ----------

CSS = """
:root{--fg:#1d1d1f;--muted:#5f6368;--line:#e3e3e3;--bg:#fff;--head:#f6f7f9;--link:#1a5fb4}
@media (prefers-color-scheme:dark){:root{--fg:#e8e8e8;--muted:#a0a0a0;--line:#3a3a3a;--bg:#161616;--head:#222;--link:#8ab4f8}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:26px;margin:0 0 6px}h2{font-size:19px;margin:34px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:16px;margin:22px 0 8px}p{margin:8px 0}a{color:var(--link)}
code{font:13px/1.4 ui-monospace,Consolas,monospace;background:var(--head);padding:1px 4px;border-radius:4px;word-break:break-all}
pre{background:var(--head);padding:12px;border-radius:6px;overflow:auto}
.tw{overflow-x:auto;margin:10px 0}table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{background:var(--head)}
.sev{display:inline-block;padding:1px 8px;border-radius:10px;color:#fff;font-size:12px;font-weight:600;white-space:nowrap}
hr{border:0;border-top:1px solid var(--line);margin:24px 0}
"""


def html_inline(text):
    out = []
    for kind, t, href in inline_tokens(text):
        e = html.escape(t)
        if kind == "bold":
            color = severity_of(t)
            out.append(f'<span class="sev" style="background:{color}">{e}</span>' if color else f"<strong>{e}</strong>")
        elif kind == "italic":
            out.append(f"<em>{e}</em>")
        elif kind == "code":
            out.append(f"<code>{e}</code>")
        elif kind == "link":
            out.append(f'<a href="{html.escape(href, quote=True)}">{e}</a>')
        else:
            out.append(e)
    return "".join(out)


def html_cell(text):
    color = severity_of(text)
    if color:
        return f'<span class="sev" style="background:{color}">{html.escape(re.sub(r"[*`]", "", text).strip())}</span>'
    return html_inline(text)


def to_html(blocks, title):
    body = []
    for kind, data in blocks:
        if kind == "h":
            level, text = data
            body.append(f"<h{level}>{html_inline(text)}</h{level}>")
        elif kind == "p":
            body.append(f"<p>{html_inline(data)}</p>")
        elif kind in ("ul", "ol"):
            body.append(nested_list_html(data, kind))
        elif kind == "table":
            head, *rows = data
            t = ["<div class='tw'><table><thead><tr>"] + [f"<th>{html_inline(c)}</th>" for c in head] + ["</tr></thead><tbody>"]
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{html_cell(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table></div>")
            body.append("".join(t))
        elif kind == "hr":
            body.append("<hr>")
        elif kind == "code":
            body.append(f"<pre><code>{html.escape(data)}</code></pre>")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>"
            f"<style>{CSS}</style></head><body><main>{''.join(body)}</main></body></html>")


def nested_list_html(items, kind):
    out, depth = [], -1
    for level, text in items:
        while depth < level:
            out.append(f"<{kind}>")
            depth += 1
        while depth > level:
            out.append(f"</{kind}>")
            depth -= 1
        out.append(f"<li>{html_inline(text)}</li>")
    out.extend(f"</{kind}>" for _ in range(depth + 1))
    return "".join(out)


# ---------- DOCX (minimal WordprocessingML) ----------

def x(t):
    return html.escape(t, quote=False)


def run(text, bold=False, italic=False, code=False, color=None, link=False, size=None):
    props = []
    if bold:
        props.append("<w:b/>")
    if italic:
        props.append("<w:i/>")
    if code:
        props.append('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>')
    if color:
        props.append(f'<w:color w:val="{color.lstrip("#")}"/>')
    if link:
        props.append('<w:color w:val="1A5FB4"/><w:u w:val="single"/>')
    if size:
        props.append(f'<w:sz w:val="{size}"/>')
    rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{x(text)}</w:t></w:r>'


class Docx:
    def __init__(self):
        self.body, self.rels = [], []

    def runs(self, text, size=None, force_bold=False):
        out = []
        for kind, t, href in inline_tokens(text):
            color = severity_of(t) if kind == "bold" else None
            if kind == "link":
                rid = f"rId{len(self.rels) + 10}"
                self.rels.append((rid, href))
                out.append(f'<w:hyperlink r:id="{rid}">{run(t, link=True, size=size)}</w:hyperlink>')
            else:
                out.append(run(t, bold=force_bold or kind == "bold", italic=kind == "italic", code=kind == "code",
                               color=color, size=size))
        return "".join(out)

    def para(self, text, style=None, numbered=None, size=None, bold=False):
        ppr = []
        if style:
            ppr.append(f'<w:pStyle w:val="{style}"/>')
        if numbered is not None:
            num_id, level = numbered
            ppr.append(f'<w:numPr><w:ilvl w:val="{level}"/><w:numId w:val="{num_id}"/></w:numPr>')
        p = f"<w:pPr>{''.join(ppr)}</w:pPr>" if ppr else ""
        return f"<w:p>{p}{self.runs(text, size=size, force_bold=bold)}</w:p>"

    def table(self, rows):
        cols = max(len(r) for r in rows)
        grid = "".join("<w:gridCol/>" for _ in range(cols))
        out = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="5000" w:type="pct"/>'
               '<w:tblBorders>' + "".join(f'<w:{b} w:val="single" w:sz="4" w:color="BFBFBF"/>'
                                          for b in ("top", "left", "bottom", "right", "insideH", "insideV")) +
               f'</w:tblBorders></w:tblPr><w:tblGrid>{grid}</w:tblGrid>']
        for ri, r in enumerate(rows):
            out.append("<w:tr>" + ("<w:trPr><w:tblHeader/></w:trPr>" if ri == 0 else ""))
            for c in r + [""] * (cols - len(r)):
                shade = '<w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/>' if ri == 0 else ""
                sev = severity_of(c) if ri else None
                content = (f"<w:p>{run(re.sub(r'[*`]', '', c).strip(), bold=True, color=sev, size=18)}</w:p>" if sev
                           else self.para(c, size=18, bold=ri == 0))
                out.append(f"<w:tc><w:tcPr>{shade}</w:tcPr>{content}</w:tc>")
            out.append("</w:tr>")
        out.append("</w:tbl><w:p/>")
        return "".join(out)

    def build(self, blocks):
        for kind, data in blocks:
            if kind == "h":
                level, text = data
                self.body.append(self.para(text, style=f"Heading{min(level, 3)}"))
            elif kind == "p":
                self.body.append(self.para(data))
            elif kind in ("ul", "ol"):
                for level, text in data:
                    self.body.append(self.para(text, numbered=(2 if kind == "ol" else 1, min(level, 2))))
            elif kind == "table":
                self.body.append(self.table(data))
            elif kind == "hr":
                self.body.append('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" w:color="BFBFBF"/></w:pBdr></w:pPr></w:p>')
            elif kind == "code":
                for line in data.split("\n"):
                    self.body.append(f"<w:p>{run(line, code=True, size=18)}</w:p>")

    def save(self, path):
        W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
        doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>{"".join(self.body)}'
               '<w:sectPr><w:pgSz w:w="15840" w:h="12240" w:orient="landscape"/>'
               '<w:pgMar w:top="1000" w:right="1000" w:bottom="1000" w:left="1000" w:header="720" w:footer="720" w:gutter="0"/>'
               '</w:sectPr></w:body></w:document>')
        styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}>'
                  '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Calibri"/>'
                  '<w:sz w:val="21"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="80"/></w:pPr></w:pPrDefault></w:docDefaults>'
                  '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
                  + "".join(f'<w:style w:type="paragraph" w:styleId="Heading{n}"><w:name w:val="heading {n}"/><w:basedOn w:val="Normal"/>'
                            f'<w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="{240 if n > 1 else 0}" w:after="80"/>'
                            f'<w:outlineLvl w:val="{n - 1}"/></w:pPr><w:rPr><w:b/><w:sz w:val="{s}"/></w:rPr></w:style>'
                            for n, s in ((1, 36), (2, 28), (3, 24)))
                  + '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>'
                  '<w:tblPr><w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>'
                  '</w:styles>')
        lvl = lambda fmt, text, i: (f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/><w:lvlText w:val="{text}"/>'
                                    f'<w:pPr><w:ind w:left="{360 * (i + 1)}" w:hanging="360"/></w:pPr></w:lvl>')
        numbering = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering {W}>'
                     '<w:abstractNum w:abstractNumId="0">' + "".join(lvl("bullet", "•", i) for i in range(3)) + '</w:abstractNum>'
                     '<w:abstractNum w:abstractNumId="1">' + "".join(lvl("decimal", f"%{i + 1}.", i) for i in range(3)) + '</w:abstractNum>'
                     '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num><w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>'
                     '</w:numbering>')
        R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    f'<Relationship Id="rId1" Type="{R}/styles" Target="styles.xml"/>'
                    f'<Relationship Id="rId2" Type="{R}/numbering" Target="numbering.xml"/>'
                    + "".join(f'<Relationship Id="{rid}" Type="{R}/hyperlink" Target="{html.escape(href, quote=True)}" TargetMode="External"/>'
                              for rid, href in self.rels)
                    + '</Relationships>')
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml",
                       '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                       '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                       '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                       '<Default Extension="xml" ContentType="application/xml"/>'
                       '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                       '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                       '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
                       '</Types>')
            z.writestr("_rels/.rels",
                       '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                       '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       f'<Relationship Id="rId1" Type="{R}/officeDocument" Target="word/document.xml"/></Relationships>')
            z.writestr("word/document.xml", doc)
            z.writestr("word/styles.xml", styles)
            z.writestr("word/numbering.xml", numbering)
            z.writestr("word/_rels/document.xml.rels", doc_rels)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report")
    ap.add_argument("--format", choices=["html", "docx"], required=True)
    ap.add_argument("--out")
    a = ap.parse_args()

    src = Path(a.report)
    md = src.read_text(encoding="utf-8")
    out = Path(a.out) if a.out else src.with_suffix("." + a.format)
    blocks = parse(md)
    title = next((d[1] for k, d in blocks if k == "h"), src.stem)
    title = re.sub(r"[*`]", "", title)

    if a.format == "html":
        out.write_text(to_html(blocks, title), encoding="utf-8")
    else:
        d = Docx()
        d.build(blocks)
        d.save(out)
    print(out)


if __name__ == "__main__":
    main()
