"""
Ingest stories and essays from Standard Ebooks via their GitHub repos.

Each Standard Ebooks book is a GitHub repo under the 'standardebooks' org.
Each story/essay is its own .xhtml file in src/epub/text/. The OPF metadata
file gives us title, author, and year. Standard Ebooks has done copyright
vetting — if it's in their catalog, it's public domain.

Run:
  python ingest/standard_ebooks.py            # ingest everything
  python ingest/standard_ebooks.py --stories  # stories only
  python ingest/standard_ebooks.py --essays   # essays only
  python ingest/standard_ebooks.py --summary  # print DB counts, no ingest
"""
import sys
import re
import time
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from bs4 import BeautifulSoup

from corpus.db import init_db, insert_work, count_by_type, get_conn

# ── Config ────────────────────────────────────────────────────────────────────

RAW_BASE = "https://raw.githubusercontent.com/standardebooks"
API_BASE = "https://api.github.com/repos/standardebooks"
HEADERS  = {"User-Agent": "bradbury-1000-nights-project"}

import os
if os.environ.get("GITHUB_TOKEN"):
    HEADERS["Authorization"] = f"token {os.environ['GITHUB_TOKEN']}"

# Boilerplate files present in every Standard Ebooks epub — skip these
SKIP_FILES = {
    "titlepage.xhtml", "colophon.xhtml", "imprint.xhtml",
    "halftitlepage.xhtml", "toc.xhtml", "uncopyright.xhtml",
    "dedication.xhtml", "epigraph.xhtml", "preface.xhtml",
    "introduction.xhtml", "foreword.xhtml", "afterword.xhtml",
    "endnotes.xhtml", "loi.xhtml", "bibliography.xhtml",
}

MIN_WORDS =   300   # skip fragments / chapter headers
MAX_WORDS = 25000   # skip full novels accidentally in a collection

# ── Repo lists (discovered by scanning the org) ────────────────────────────────

STORY_REPOS = [
    "a-n-afanasyev_russian-folktales_leonard-a-magnus",
    "akutagawa-ryunosuke_short-fiction_various-translators",
    "aleksandr-kuprin_short-fiction_various-translators",
    "algernon-blackwood_john-silence-stories",
    "ambrose-bierce_can-such-things-be",
    "anton-chekhov_short-fiction_constance-garnett",
    "arthur-machen_short-fiction",
    "beatrix-potter_short-fiction",
    "catherine-louisa-pirkis_short-fiction",
    "catherine-louisa-pirkis_the-experiences-of-loveday-brooke-lady-detective",
    "e-f-benson_ghost-stories",
    "e-m-forster_short-fiction",
    "edgar-allan-poe_short-fiction",
    "ernest-hemingway_short-fiction",
    "f-scott-fitzgerald_short-fiction",
    "fyodor-sologub_short-fiction_various-translators",
    "george-macdonald_short-fiction",
    "gustave-flaubert_short-fiction_m-walter-dunne",
    "guy-de-maupassant_short-fiction_various-translators",
    "h-g-wells_short-fiction",
    "h-p-lovecraft_short-fiction",
    "h-rider-haggard_allan-quatermain-stories",
    "herman-melville_short-fiction",
    "hjalmar-soderberg_short-fiction_various-translators",
    "ivan-bunin_short-fiction_various-translators",
    "j-sheridan-le-fanu_short-fiction",
    "jacob-grimm_wilhelm-grimm_household-tales_margaret-hunt",
    "james-stephens_irish-fairy-tales",
    "jonas-lie_short-fiction_various-translators",
    "kate-chopin_short-fiction",
    "leo-tolstoy_short-fiction_various-translators",
    "leonid-andreyev_short-fiction_various-translators",
    "lord-dunsany_fifty-one-tales",
    "m-r-james_short-fiction",
    "mary-shelley_short-fiction",
    "nella-larsen_short-fiction",
    "nikolai-gogol_short-fiction_various-translators",
    "o-henry_short-fiction",
    "oscar-wilde_childrens-stories",
    "oscar-wilde_lord-arthur-saviles-crime-and-other-stories",
    "p-g-wodehouse_golf-stories",
    "p-g-wodehouse_jeeves-stories",
    "p-g-wodehouse_mr-mulliner-stories",
    "p-g-wodehouse_short-fiction",
    "ring-lardner_jack-keefe-stories",
    "ring-lardner_short-fiction",
    "rudyard-kipling_just-so-stories",
    "rudyard-kipling_the-jungle-book",
    "saki_short-fiction",
    "selma-lagerlof_short-fiction_various-translators",
    "thomas-hardy_short-fiction",
    "vladimir-korolenko_short-fiction_various-translators",
    "voltairine-de-cleyre_short-fiction",
    "vsevolod-garshin_short-fiction_rowland-smith",
    "xavier-de-maistre_short-fiction_various-translators",
    "zitkala-sa_american-indian-stories",
    # Folktale / fairy tale collections
    "frank-hamilton-cushing_zuni-folktales",
    "joseph-jacobs_indian-fairy-tales",
    "stanley-g-weinbaum_short-fiction",
    # Detective / genre
    "dashiell-hammett_continental-op-stories",
]

ESSAY_REPOS = [
    "ralph-waldo-emerson_essays",
    "henry-david-thoreau_essays",
    "william-hazlitt_table-talk",
    "robert-louis-stevenson_travel-essays",
    "thomas-paine_essays",
    "errico-malatesta_essays_various-translators",
    # added round 2
    "g-k-chesterton_heretics",
    "g-k-chesterton_orthodoxy",
    "g-k-chesterton_whats-wrong-with-the-world",
    "max-beerbohm_the-works-of-max-beerbohm",
]

# ── GitHub helpers ─────────────────────────────────────────────────────────────

def gh_get(url: str) -> dict | list | None:
    for attempt in range(3):
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 403:
            wait = int(r.headers.get("Retry-After", 60))
            print(f"  Rate limited — waiting {wait}s...")
            time.sleep(wait)
        elif r.status_code == 404:
            return None
        else:
            return None
    return None


def get_text_files(repo: str) -> list[str]:
    data = gh_get(f"{API_BASE}/{repo}/contents/src/epub/text")
    if not data:
        return []
    return [
        f["name"] for f in data
        if isinstance(f, dict)
        and f["name"].endswith(".xhtml")
        and f["name"] not in SKIP_FILES
    ]


def get_metadata(repo: str) -> dict:
    url = f"{RAW_BASE}/{repo}/master/src/epub/content.opf"
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        return {}
    soup = BeautifulSoup(r.text, "xml")

    short_title = soup.find("meta", property="se:short-title")
    dc_title     = soup.find("dc:title")
    title = (short_title.get_text(strip=True) if short_title
             else dc_title.get_text(strip=True) if dc_title else "")

    creator = soup.find("dc:creator")
    author  = creator.get_text(strip=True) if creator else ""

    dc_date = soup.find("dc:date")
    year = None
    if dc_date:
        m = re.search(r"\d{4}", dc_date.get_text())
        if m:
            year = int(m.group())

    return {"title": title, "author": author, "year": year}


def parse_xhtml(repo: str, filename: str) -> str | None:
    url = f"{RAW_BASE}/{repo}/master/src/epub/text/{filename}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    for el in soup.select("section#endnotes, aside"):
        el.decompose()
    paragraphs = [p.get_text(separator=" ", strip=True) for p in soup.find_all("p")]
    paragraphs = [p for p in paragraphs if len(p) > 20]
    return "\n\n".join(paragraphs) if paragraphs else None


def title_from_xhtml(repo: str, filename: str) -> str:
    """Try to get the real title from the <h2> in the file; fall back to slug."""
    url = f"{RAW_BASE}/{repo}/master/src/epub/text/{filename}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        return slug_to_title(filename)
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in ("h2", "h3", "h1"):
        el = soup.find(tag)
        if el:
            text = el.get_text(separator=" ", strip=True)
            if text and len(text) < 120:
                return text
    return slug_to_title(filename)


def slug_to_title(filename: str) -> str:
    return filename.replace(".xhtml", "").replace("-", " ").title()


# ── Ingest one repo ────────────────────────────────────────────────────────────

def ingest_repo(repo: str, work_type: str) -> tuple[int, int]:
    """Returns (added, skipped) counts."""
    meta = get_metadata(repo)
    if not meta.get("author"):
        print(f"  {repo}: no metadata, skipping")
        return 0, 0

    files = get_text_files(repo)
    if not files:
        print(f"  {repo}: no text files found")
        return 0, 0

    source_url = "https://standardebooks.org/ebooks/" + repo.replace("_", "/", 1)
    added, skipped = 0, 0

    for filename in files:
        # Get title from the actual file header
        title = title_from_xhtml(repo, filename)
        text  = parse_xhtml(repo, filename)

        if not text:
            skipped += 1
            continue

        wc = len(text.split())

        if wc < MIN_WORDS:
            skipped += 1
            continue
        if wc > MAX_WORDS:
            skipped += 1
            continue

        insert_work(
            type=work_type,
            title=title,
            author=meta["author"],
            year=meta["year"],
            word_count=wc,
            text=text,
            source_url=source_url,
            source_name="Standard Ebooks",
        )
        added += 1
        time.sleep(0.05)

    return added, skipped


# ── Summary table ──────────────────────────────────────────────────────────────

def print_summary():
    counts = count_by_type()
    print("\n" + "="*50)
    print(f"{'Type':<10} {'Count':>8}  {'Target':>8}  {'Status'}")
    print("-"*50)
    for t, target in [("poem", 1000), ("story", 1000), ("essay", 1000)]:
        n = counts.get(t, 0)
        bar = "✓" if n >= target else f"{n/target*100:.0f}% of target"
        print(f"{t:<10} {n:>8,}  {target:>8,}  {bar}")
    print("="*50)

    # Author breakdown for stories and essays
    with get_conn() as conn:
        for t in ("story", "essay"):
            rows = conn.execute(
                "SELECT author, COUNT(*) as n, AVG(word_count) as avg_wc "
                "FROM works WHERE type=? GROUP BY author ORDER BY n DESC LIMIT 20",
                (t,)
            ).fetchall()
            if rows:
                print(f"\nTop {t} authors:")
                for r in rows:
                    print(f"  {r['author']:<40} {r['n']:>4} works  ~{int(r['avg_wc']):,} words avg")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stories", action="store_true")
    parser.add_argument("--essays",  action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    init_db()

    if args.summary:
        print_summary()
        return

    # Default: run both
    run_stories = args.stories or (not args.stories and not args.essays)
    run_essays  = args.essays  or (not args.stories and not args.essays)

    if run_stories:
        print(f"\n{'='*60}\nINGESTING STORIES ({len(STORY_REPOS)} repos)\n{'='*60}")
        total_added = total_skipped = 0
        for repo in STORY_REPOS:
            print(f"\n  {repo}")
            added, skipped = ingest_repo(repo, "story")
            print(f"    → {added} added, {skipped} skipped")
            total_added   += added
            total_skipped += skipped
            time.sleep(0.2)
        print(f"\nStories: {total_added} added, {total_skipped} skipped")

    if run_essays:
        print(f"\n{'='*60}\nINGESTING ESSAYS ({len(ESSAY_REPOS)} repos)\n{'='*60}")
        total_added = total_skipped = 0
        for repo in ESSAY_REPOS:
            print(f"\n  {repo}")
            added, skipped = ingest_repo(repo, "essay")
            print(f"    → {added} added, {skipped} skipped")
            total_added   += added
            total_skipped += skipped
            time.sleep(0.2)
        print(f"\nEssays: {total_added} added, {total_skipped} skipped")

    print_summary()


if __name__ == "__main__":
    main()
