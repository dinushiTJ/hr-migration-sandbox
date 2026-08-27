"""
Inject one exported run into the visual replay page.

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

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "viz" / "template.html"
RUN = ROOT / "out" / "run.json"
README = ROOT / "README.md"
TOOLS = ROOT / "viz" / "tools.json"
OUT = ROOT / "out" / "control_room.html"


def validation_html():
    """Run the validity checks and colourise their output for the page.

    Run rather than cached, so the page can never show a green result from an
    earlier state of the code.
    """
    r = subprocess.run([sys.executable, str(ROOT / "src" / "validate.py")],
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
    """Rewrite the README's tool table from viz/tools.json.

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


def main():
    data = RUN.read_text()
    page = TEMPLATE.read_text()
    if "__RUN_DATA__" not in page:
        raise SystemExit("template is missing the __RUN_DATA__ placeholder")

    # Guard against the one thing that would silently break the page: a literal
    # </script> inside the data would close the block early.
    data = data.replace("</", "<\\/")

    n = json.loads(RUN.read_text())
    page = page.replace("__RUN_DATA__", data)
    page = page.replace("__TOOLS__", TOOLS.read_text().replace("</", "<\\/"))
    page = page.replace("__VALIDATION__", validation_html())
    sync_readme_tools()
    page = page.replace("__DOCS__", render_markdown(README.read_text()))
    page = page.replace(
        "943 legacy HR, payroll and org records", f"{len(n['events'])} legacy HR, payroll and org records")
    page = page.replace('max="943"', f'max="{len(n["events"])}"')
    page = page.replace(">943</span>", f">{len(n['events'])}</span>")
    OUT.write_text(page)
    print(f"{OUT.name}  {OUT.stat().st_size/1024:.0f} KB  {len(n['events'])} events"
          f"  + README and validity checks")


if __name__ == "__main__":
    main()
