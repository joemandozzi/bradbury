"""
build.py — entry point for the static site generator.

Usage:
  python build.py              # build today's page
  python build.py 2026-06-10   # build a specific date

Output goes to site/. Open site/index.html in a browser.
"""
import sys
import shutil
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from corpus.db import init_db, count_by_type
from picker import pick_for_date, reading_time_minutes


# ── paths ──────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent
TEMPLATES = ROOT / "templates"
STATIC    = ROOT / "static"
SITE      = ROOT / "site"


# ── Jinja2 custom filters ──────────────────────────────────────────────────
def nl2br(text):
    """Convert newlines to <br> tags (used for poem text)."""
    from markupsafe import Markup, escape
    return Markup(escape(text).replace("\n", Markup("<br>\n")))

def wordcount_label(n):
    """'~400 words · ~2 min read'"""
    n = int(n or 0)
    if n == 0:
        return ""
    mins = max(1, round(n / 200))  # ~200 wpm for literary reading
    return f"~{n:,} words · ~{mins} min read"


# ── build ──────────────────────────────────────────────────────────────────
def build(target_date: date):
    init_db()

    counts = count_by_type()
    if sum(counts.values()) == 0:
        print("Database is empty. Run the ingest scripts first.")
        print("  python ingest/poems.py")
        print("  python ingest/essays.py")
        print("  python ingest/stories.py")
        # Build a placeholder page instead of failing.

    SITE.mkdir(exist_ok=True)

    # Copy static assets.
    dest_static = SITE / "static"
    if dest_static.exists():
        shutil.rmtree(dest_static)
    shutil.copytree(STATIC, dest_static)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
    env.filters["nl2br"] = nl2br
    env.filters["wordcount_label"] = wordcount_label

    triad = pick_for_date(target_date)
    date_display = target_date.strftime("%B %-d, %Y")  # e.g. "June 10, 2026"
    read_time    = reading_time_minutes(triad)

    # Render the day page.
    day_tmpl = env.get_template("day.html")
    day_html = day_tmpl.render(
        root="",
        date_iso=target_date.isoformat(),
        date_display=date_display,
        read_time=read_time,
        story=triad.get("story"),
        poem=triad.get("poem"),
        essay=triad.get("essay"),
    )
    (SITE / "index.html").write_text(day_html, encoding="utf-8")

    # Also write a permalink for the date.
    dated_dir = SITE / target_date.isoformat()
    dated_dir.mkdir(exist_ok=True)
    day_html_dated = day_tmpl.render(
        root="../",
        date_iso=target_date.isoformat(),
        date_display=date_display,
        read_time=read_time,
        story=triad.get("story"),
        poem=triad.get("poem"),
        essay=triad.get("essay"),
    )
    (dated_dir / "index.html").write_text(day_html_dated, encoding="utf-8")

    # Render the about page.
    about_html = env.get_template("about.html").render(root="")
    (SITE / "about.html").write_text(about_html, encoding="utf-8")

    print(f"Built site/ for {date_display}")
    print(f"  story : {triad['story']['title'] if triad.get('story') else 'none'}")
    print(f"  poem  : {triad['poem']['title']  if triad.get('poem')  else 'none'}")
    print(f"  essay : {triad['essay']['title'] if triad.get('essay') else 'none'}")
    print(f"Open: site/index.html")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    else:
        target = date.today()
    build(target)
