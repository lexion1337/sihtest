"""
make_brief.py -- render README.md as a printable one-file HTML briefing.

    python tools/make_brief.py        ->  team_brief.html

Open that file in any browser and use Ctrl+P -> "Save as PDF" to get a PDF to
send to the team. That route is deliberate: converting to PDF properly would
mean adding pandoc or reportlab, and this project takes no new dependencies
without a reason. The browser already has a PDF writer in it.

This is a SMALL markdown subset, matched to how README.md is actually written
(headings, tables, lists, block quotes, rules, bold/italic/code). It is not a
general markdown implementation and should not be reused as one. If the README
grows a construct this does not handle, the construct will appear verbatim
rather than silently vanishing -- that is the intended failure mode.
"""

import html
import io
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "README.md")
OUT = os.path.join(HERE, "team_brief.html")

CSS = """
:root{
  --page:#FFFFFF; --ink:#241B12; --ink2:#5F4B39; --rule:#E0D3C2;
  --rule2:#CDBBA4; --action:#7C4A21; --actionbg:#F4E9DD; --note:#F2E9DA;
  --serif:"Sitka Banner","Sitka Text",Constantia,"Palatino Linotype",Georgia,serif;
  --text:"Sitka Text",Constantia,Georgia,"Palatino Linotype",serif;
  --sans:"Segoe UI",-apple-system,Roboto,"Helvetica Neue",Arial,sans-serif;
}
*{box-sizing:border-box}
body{background:#F7F3EC;color:var(--ink);margin:0;padding:34px 18px 60px;
     font:17px/1.6 var(--text);
     font-variant-numeric:lining-nums tabular-nums}
.sheet{max-width:820px;margin:0 auto;background:var(--page);padding:54px 62px;
       border:1px solid var(--rule);border-radius:4px}
h1,h2,h3{font-family:var(--serif);font-weight:600;letter-spacing:-.015em;
         line-height:1.15}
h1{font-size:40px;margin:0 0 6px}
h2{font-size:25px;margin:38px 0 10px;padding-bottom:7px;
   border-bottom:2px solid var(--rule2)}
h3{font-size:20px;margin:26px 0 8px}
p{margin:12px 0}
ul,ol{margin:12px 0;padding-left:24px}
li{margin:7px 0}
strong{font-weight:600}
code{font-family:var(--sans);font-size:14px;background:#F2EBE1;
     border:1px solid var(--rule);border-radius:4px;padding:1px 5px}
pre{background:#F2EBE1;border:1px solid var(--rule);border-radius:8px;
    padding:14px 16px;overflow-x:auto;font:13px/1.5 "Cascadia Mono",Consolas,monospace}
blockquote{margin:16px 0;padding:12px 18px;background:var(--actionbg);
           border-left:5px solid var(--action);border-radius:0 8px 8px 0}
blockquote p{margin:6px 0}
table{border-collapse:collapse;width:100%;margin:14px 0;font-family:var(--sans);
      font-size:15px}
th{text-align:left;font-size:12.5px;letter-spacing:.04em;text-transform:uppercase;
   color:var(--ink2);padding:9px 10px;border-bottom:2px solid var(--rule2)}
td{padding:8px 10px;border-bottom:1px solid var(--rule);vertical-align:top}
hr{border:0;border-top:1px solid var(--rule);margin:30px 0}
a{color:var(--action)}
.sub{font-family:var(--sans);font-size:15px;color:var(--ink2);margin:0 0 4px}

/* Print: the whole point of the file. Keep headings with their sections and
   never split a table across a page break. */
@media print{
  body{background:#FFF;padding:0;font-size:11.5pt}
  .sheet{max-width:none;border:0;border-radius:0;padding:0}
  .noprint{display:none}
  h2,h3{break-after:avoid-page}
  table,blockquote,pre{break-inside:avoid-page}
  a{color:var(--ink);text-decoration:none}
  @page{margin:16mm 14mm}
}
.banner{background:var(--note);border:1px solid var(--rule2);border-radius:8px;
        padding:14px 18px;margin-bottom:26px;font-family:var(--sans);font-size:15px}
"""


def inline(t):
    """Bold, italic, inline code, links -- applied to already-escaped text."""
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\w)", r"<em>\1</em>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
    return t


def esc(t):
    return inline(html.escape(t, quote=False))


def is_table_sep(line):
    return bool(re.match(r"^\s*\|[\s:|-]+\|\s*$", line)) and "-" in line


def cells(line):
    parts = line.strip().split("|")
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [p.strip() for p in parts]


def convert(md):
    out, i = [], 0
    lines = md.split("\n")
    while i < len(lines):
        ln = lines[i]

        # fenced code
        if ln.startswith("```"):
            body, i = [], i + 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i]); i += 1
            i += 1
            out.append("<pre>%s</pre>" % html.escape("\n".join(body), quote=False))
            continue

        # table: a header row followed by a |---| separator
        if ln.strip().startswith("|") and i + 1 < len(lines) and is_table_sep(lines[i + 1]):
            head = cells(ln); i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i])); i += 1
            out.append("<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (
                "".join("<th>%s</th>" % esc(c) for c in head),
                "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % esc(c) for c in r)
                        for r in rows)))
            continue

        # block quote
        if ln.startswith(">"):
            body = []
            while i < len(lines) and lines[i].startswith(">"):
                body.append(lines[i].lstrip(">").strip()); i += 1
            paras = "\n".join(body).split("\n\n")
            out.append("<blockquote>%s</blockquote>"
                       % "".join("<p>%s</p>" % esc(p.replace("\n", " "))
                                 for p in paras if p.strip()))
            continue

        # lists (ordered and unordered), including wrapped continuation lines
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", ln)
        if m:
            tag = "ol" if m.group(2)[0].isdigit() else "ul"
            items = []
            while i < len(lines):
                m2 = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if m2:
                    items.append(m2.group(3)); i += 1
                elif lines[i].startswith("   ") and lines[i].strip() and items:
                    items[-1] += " " + lines[i].strip(); i += 1
                else:
                    break
            out.append("<%s>%s</%s>" % (
                tag, "".join("<li>%s</li>" % esc(x) for x in items), tag))
            continue

        if re.match(r"^#{1,6}\s", ln):
            lvl = len(ln) - len(ln.lstrip("#"))
            out.append("<h%d>%s</h%d>" % (min(lvl, 3), esc(ln.lstrip("# ").strip()),
                                          min(lvl, 3)))
            i += 1
            continue

        if re.match(r"^---+\s*$", ln):
            out.append("<hr>"); i += 1; continue

        if not ln.strip():
            i += 1; continue

        # paragraph: gather until a blank line or a block construct
        body = []
        while i < len(lines) and lines[i].strip() \
                and not re.match(r"^(#{1,6}\s|>|```|---+\s*$|\s*([-*]|\d+\.)\s)", lines[i]) \
                and not lines[i].strip().startswith("|"):
            body.append(lines[i].strip()); i += 1
        if body:
            out.append("<p>%s</p>" % esc(" ".join(body)))
    return "\n".join(out)


def main():
    md = io.open(SRC, encoding="utf-8").read()
    page = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<title>Skill Drift Analyzer -- team briefing</title>\n'
        "<style>%s</style>\n</head>\n<body>\n<div class=\"sheet\">\n"
        '<div class="banner noprint"><b>To save this as a PDF:</b> press '
        "Ctrl+P (Cmd+P on a Mac), then choose <b>Save as PDF</b> as the "
        "destination. This box will not appear in the PDF.</div>\n"
        "%s\n</div>\n</body>\n</html>\n" % (CSS, convert(md))
    )
    io.open(OUT, "w", encoding="utf-8").write(page)
    print("wrote %s (%d KB) from %s"
          % (os.path.relpath(OUT, HERE), len(page) // 1024,
             os.path.relpath(SRC, HERE)))
    print("Open it and press Ctrl+P -> Save as PDF.")


if __name__ == "__main__":
    main()
