"""
Inject one exported run into the visual replay page, and build the
documentation page from the README beside it.

The page is a view over the pipeline's own output: every count, amount and
rejection reason it displays comes from out/run.json, which is derived from the
SQLite target. Nothing is retyped, so the page cannot drift from the run.
"""
import html
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from markdown_lite import render as render_markdown
from site_chrome import head_assets, nav, repo_links

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "site" / "assets" / "template.html"
DOCS_TEMPLATE = ROOT / "site" / "assets" / "docs.html"
RUN = ROOT / "out" / "run.json"
README = ROOT / "README.md"
TOOLS = ROOT / "site" / "assets" / "tools.json"
OUT = ROOT / "out" / "control_room.html"
DOCS_OUT = ROOT / "out" / "docs.html"


def validation_html():
    """Run the validity checks and colourise their output for the page.

    Run rather than cached, so the page can never show a green result from an
    earlier state of the code.
    """
    r = subprocess.run([sys.executable, str(ROOT / "pipeline" / "validate.py")],
                       capture_output=True, text=True)
    lines = []
    for line in (r.stdout or "validity checks did not run").split("\n"):
        esc = html.escape(line)
        for status in ("PASS", "FAIL", "KNOWN"):
            token = "  " + status + " "
            if line.startswith(token):
                esc = (f'  <span class="st {status}">{status}</span>'
                       + html.escape(line[len(token):]))
                break
        lines.append(esc)
    return "\n".join(lines)


def sync_readme_tools():
    """Rewrite the README's tool table from site/assets/tools.json.

    The page renders the same data as chips. Keeping two hand-maintained copies
    is how a reference table quietly goes stale, so there is one source and the
    README section between the markers is generated from it.
    """
    tools = json.loads(TOOLS.read_text())
    rows = ["| Step | In this sandbox | In production |", "|---|---|---|"]
    for st in tools["stages"]:
        names = ", ".join(t["n"] for t in st["tools"])
        rows.append(f"| **{st['stage']}** | {st['here']} | {names} |")
    table = "\n".join(rows)

    md = README.read_text()
    start, end = "<!-- TOOLS:START -->", "<!-- TOOLS:END -->"
    if start in md and end in md:
        head, rest = md.split(start, 1)
        _, tail = rest.split(end, 1)
        README.write_text(f"{head}{start}\n{table}\n{end}{tail}")


def doc_data(n):
    """The handful of figures the documentation's explanatory diagrams quote,
    taken from the run rather than typed into the template."""
    rules = {r["rule_id"]: r for r in n["rules"]}
    workers = [e for e in n["events"] if e["e"] == "worker"]
    return {
        "control": n["control"],
        "flagged": sum(r["n"] for r in n["rules"] if r["disposition"] == "LOADED_FLAGGED"),
        "worker_source": len(workers),
        "worker_rejected": sum(1 for e in workers if e["o"] == "rejected"),
        "worker_flagged": sum(1 for e in workers if e["o"] == "flagged"),
        "overlaps": rules.get("CMP-008", {}).get("n", 0),
        "cascade": rules.get("CMP-001", {}).get("n", 0),
    }


def build_docs(n):
    """The README as its own page, with the validity checks placed after the
    section that explains how the work was verified."""
    sync_readme_tools()
    body = repo_links(render_markdown(README.read_text()))
    checks = ('<h2 id="validity-checks">Validity checks</h2>\n'
              "<p>Re-derived from the database and the source files, without importing the "
              "pipeline, so a bug shared between the loader and its own reconciliation cannot "
              "hide from them. A defect already documented under Known issues is marked KNOWN "
              "rather than FAIL. This output is produced fresh on every build.</p>\n"
              f'<pre class="checks-out">{validation_html()}</pre>\n')
    marker = '<h2 id="known-issues">'
    body = body.replace(marker, checks + marker, 1) if marker in body else body + checks

    page = DOCS_TEMPLATE.read_text()
    page = page.replace("__HEAD__", head_assets()).replace("__NAV__", nav("docs.html"))
    page = page.replace("__DOC_DATA__", json.dumps(doc_data(n)).replace("</", "<\\/"))
    page = page.replace("__DOCS__", body)
    DOCS_OUT.write_text(page)
    print(f"{DOCS_OUT.name}  {DOCS_OUT.stat().st_size/1024:.0f} KB  README and validity checks")


def main():
    data = RUN.read_text()
    page = TEMPLATE.read_text()
    if "__RUN_DATA__" not in page:
        raise SystemExit("template is missing the __RUN_DATA__ placeholder")

    # Guard against the one thing that would silently break the page: a literal
    # </script> inside the data would close the block early.
    data = data.replace("</", "<\\/")

    n = json.loads(RUN.read_text())
    page = page.replace("__HEAD__", head_assets()).replace("__NAV__", nav("control_room.html"))
    page = page.replace("__RUN_DATA__", data)
    page = page.replace("__TOOLS__", TOOLS.read_text().replace("</", "<\\/"))
    page = page.replace(
        "943 legacy HR, payroll and org records", f"{len(n['events'])} legacy HR, payroll and org records")
    page = page.replace('max="943"', f'max="{len(n["events"])}"')
    page = page.replace(">943</span>", f">{len(n['events'])}</span>")
    OUT.write_text(page)
    print(f"{OUT.name}  {OUT.stat().st_size/1024:.0f} KB  {len(n['events'])} events")
    build_docs(n)


if __name__ == "__main__":
    main()
