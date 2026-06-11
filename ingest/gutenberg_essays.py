"""
gutenberg_essays.py — ingest essays from Project Gutenberg.

Sources:
  spectator  — The Spectator (Addison & Steele, 1711-1712), Gutenberg #12030
  montaigne  — Essays of Montaigne (Florio translation), Gutenberg #3600
  bacon      — Essays (Francis Bacon, 1625), Gutenberg #575
  lamb       — Essays of Elia (Charles Lamb, 1823), Gutenberg #10343

Usage:
  python ingest/gutenberg_essays.py              # all four sources
  python ingest/gutenberg_essays.py spectator    # one source
"""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from corpus.db import init_db, insert_work, count_by_type

MIN_WORDS = 200
MAX_WORDS = 15_000

GUTENBERG_BASE = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"


# ── helpers ────────────────────────────────────────────────────────────────────

def fetch_gutenberg(book_id: int) -> str:
    url = GUTENBERG_BASE.format(id=book_id)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.text


def strip_boilerplate(text: str) -> str:
    """Remove Gutenberg header and footer."""
    start_markers = ["*** START OF THE PROJECT GUTENBERG EBOOK", "***START OF THE PROJECT GUTENBERG EBOOK"]
    end_markers = ["*** END OF THE PROJECT GUTENBERG EBOOK", "***END OF THE PROJECT GUTENBERG EBOOK"]
    for m in start_markers:
        idx = text.find(m)
        if idx != -1:
            text = text[text.index("\n", idx) + 1:]
            break
    for m in end_markers:
        idx = text.find(m)
        if idx != -1:
            text = text[:idx]
            break
    return text


def clean_text(text: str) -> str:
    """Normalize whitespace."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse 3+ blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def word_count(text: str) -> int:
    return len(text.split())


def insert(title, author, year, text, source_url, source_name):
    wc = word_count(text)
    if wc < MIN_WORDS:
        return False, "too short"
    if wc > MAX_WORDS:
        return False, "too long"
    ok = insert_work(
        type="essay",
        title=title,
        author=author,
        year=year,
        word_count=wc,
        text=text,
        source_url=source_url,
        source_name=source_name,
    )
    return ok, None


# ── The Spectator ──────────────────────────────────────────────────────────────

SPECTATOR_AUTHORS = {
    "Addison": "Joseph Addison",
    "Steele": "Richard Steele",
    "Tickell": "Thomas Tickell",
    "Budgell": "Eustace Budgell",
    "Grove": "Henry Grove",
    "Hughes": "John Hughes",
    "Parnell": "Thomas Parnell",
    "Pope": "Alexander Pope",
    "Philips": "Ambrose Philips",
    "Byrom": "John Byrom",
}


def ingest_spectator(text: str) -> tuple[int, int]:
    """
    Each issue is delimited by a line like:
      No. 2.                 Friday, March 2, 1711.                Steele.
    We split on those markers and extract number, date, author, and body.
    """
    # Pattern: "No. NNN." possibly with lots of spaces, then day/date, then author surname.
    marker = re.compile(
        r"^No\.\s+(\d+)\.\s+\w+day,\s+\w+\s+\d+,\s+(\d{4})\.\s+([\w\-]+)\.\s*$",
        re.MULTILINE,
    )

    added = skipped = 0
    matches = list(marker.finditer(text))
    print(f"  Found {len(matches)} Spectator issues")

    for i, m in enumerate(matches):
        number = m.group(1)
        year = int(m.group(2))
        surname = m.group(3)
        author = SPECTATOR_AUTHORS.get(surname, f"{surname}")

        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = clean_text(text[body_start:body_end])

        # Skip the index/notes section at end of file (issues appear again in notes)
        if year < 1710 or year > 1715:
            skipped += 1
            continue

        title = f"The Spectator, No. {number}"
        source_url = f"https://www.gutenberg.org/ebooks/12030"
        ok, reason = insert(title, author, year, body, source_url, "Project Gutenberg")
        if ok:
            added += 1
        else:
            skipped += 1

    return added, skipped


# ── Montaigne ─────────────────────────────────────────────────────────────────

def ingest_montaigne(text: str) -> tuple[int, int]:
    """
    Each essay starts with:
      CHAPTER [ROMAN NUMERAL]
      (blank line)
      TITLE IN CAPS
    """
    # Find all chapter positions
    chapter_pat = re.compile(r"^(CHAPTER [IVXLCDM]+)\s*\n\n([A-Z][A-Z ,'\-;?]+\.?)\s*\n", re.MULTILINE)
    matches = list(chapter_pat.finditer(text))
    print(f"  Found {len(matches)} Montaigne chapters")

    added = skipped = 0
    for i, m in enumerate(matches):
        title_line = m.group(2).strip().title()
        title = f"Of {title_line}" if not title_line.lower().startswith(("that ", "of ", "on ", "how ", "whether ", "to ")) else title_line

        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = clean_text(text[body_start:body_end])

        source_url = "https://www.gutenberg.org/ebooks/3600"
        ok, reason = insert(title, "Michel de Montaigne", 1580, body, source_url, "Project Gutenberg")
        if ok:
            added += 1
        else:
            skipped += 1

    return added, skipped


# ── Bacon ─────────────────────────────────────────────────────────────────────

def ingest_bacon(text: str) -> tuple[int, int]:
    """
    Each essay title appears as a standalone line: "Of Truth", "Of Studies", etc.
    Must be short (< 60 chars), start with "Of ", title case, followed by body text.
    """
    # Match lines that are just an essay title: "Of Xyz" or "Of Xyz and Xyz"
    essay_pat = re.compile(
        r"^(Of\s[A-Z][A-Za-z ,'\-]+?)$",
        re.MULTILINE,
    )
    matches = list(essay_pat.finditer(text))
    # Filter out table-of-contents entries (TOC has many in a row with no content between)
    # Keep only matches where the body between this and the next marker has > 100 words
    candidates = []
    for i, m in enumerate(matches):
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        if word_count(body) > 100:
            candidates.append((m, body))

    print(f"  Found {len(candidates)} Bacon essays (after filtering TOC)")

    added = skipped = 0
    for m, body in candidates:
        title = m.group(1).strip()
        body = clean_text(body)
        source_url = "https://www.gutenberg.org/ebooks/575"
        ok, reason = insert(title, "Francis Bacon", 1625, body, source_url, "Project Gutenberg")
        if ok:
            added += 1
        else:
            skipped += 1

    return added, skipped


# ── Charles Lamb ──────────────────────────────────────────────────────────────

def ingest_lamb(text: str) -> tuple[int, int]:
    """
    Each essay title is an ALL-CAPS heading on its own line, e.g.:
      THE SOUTH-SEA HOUSE
      OXFORD IN THE VACATION
    """
    # Only grab the Elia section (before the Notes/Appendix)
    elia_start = text.find("ELIA\n")
    notes_start = text.find("\nNOTES\n")
    if elia_start == -1:
        print("  Could not find ELIA section")
        return 0, 0
    end = notes_start if notes_start != -1 else len(text)
    text = text[elia_start:end]

    # Match all-caps title lines (3+ words or 1 long word, not section headers)
    title_pat = re.compile(
        r"^([A-Z][A-Z\s,':\-]{8,}[A-Z])$",
        re.MULTILINE,
    )
    matches = list(title_pat.finditer(text))
    # Filter out ELIA, THE LAST ESSAYS OF ELIA, CONTENTS etc.
    skip_titles = {"ELIA", "THE LAST ESSAYS OF ELIA", "CONTENTS", "APPENDIX", "INTRODUCTION"}
    matches = [m for m in matches if m.group(1).strip() not in skip_titles and
               not m.group(1).startswith("_")]

    print(f"  Found {len(matches)} Lamb essays")

    added = skipped = 0
    for i, m in enumerate(matches):
        title = m.group(1).strip().title()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = clean_text(text[body_start:body_end])

        source_url = "https://www.gutenberg.org/ebooks/10343"
        ok, reason = insert(title, "Charles Lamb", 1823, body, source_url, "Project Gutenberg")
        if ok:
            added += 1
        else:
            skipped += 1

    return added, skipped


# ── Samuel Johnson's Rambler ──────────────────────────────────────────────────

def ingest_johnson(texts: list[str]) -> tuple[int, int]:
    """
    Each Rambler essay starts with a line like:
      No. 1. TUESDAY, MARCH 20, 1749-50.
    Spread across two Gutenberg volumes (43656 and 11397).
    """
    marker = re.compile(
        r"^No\.\s+(\d+)\.\s+\w+DAY,\s+\w+\s+\d+,\s+[\d\-]+\.\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    added = skipped = 0
    for text in texts:
        matches = list(marker.finditer(text))
        for i, m in enumerate(matches):
            number = m.group(1)
            body_start = m.end()
            body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = clean_text(text[body_start:body_end])

            title = f"The Rambler, No. {number}"
            source_url = "https://www.gutenberg.org/ebooks/43656"
            ok, reason = insert(title, "Samuel Johnson", 1750, body, source_url, "Project Gutenberg")
            if ok:
                added += 1
            else:
                skipped += 1

    return added, skipped


# ── main ──────────────────────────────────────────────────────────────────────

SOURCES = {
    "spectator": (12030, "The Spectator", ingest_spectator),
    "montaigne": (3600,  "Montaigne's Essays", ingest_montaigne),
    "bacon":     (575,   "Bacon's Essays", ingest_bacon),
    "lamb":      (10343, "Essays of Elia", ingest_lamb),
    # johnson handled specially (two volumes)
}

JOHNSON_IDS = [43656, 11397]  # Rambler Vol I, Vol II


def run(names: list[str]):
    init_db()
    for name in names:
        if name == "johnson":
            print(f"\n{'='*60}\nSamuel Johnson's Rambler (Gutenberg #43656 + #11397)\n{'='*60}")
            texts = []
            for gid in JOHNSON_IDS:
                print(f"  Downloading #{gid}...", flush=True)
                try:
                    raw = fetch_gutenberg(gid)
                    texts.append(clean_text(strip_boilerplate(raw)))
                except Exception as e:
                    print(f"  FETCH ERROR #{gid}: {e}")
                time.sleep(1)
            if texts:
                added, skipped = ingest_johnson(texts)
                print(f"  → {added} added, {skipped} skipped")
            continue

        book_id, label, fn = SOURCES[name]
        print(f"\n{'='*60}\n{label} (Gutenberg #{book_id})\n{'='*60}")
        print("  Downloading...", flush=True)
        try:
            raw = fetch_gutenberg(book_id)
        except Exception as e:
            print(f"  FETCH ERROR: {e}")
            continue
        text = clean_text(strip_boilerplate(raw))
        added, skipped = fn(text)
        print(f"  → {added} added, {skipped} skipped")
        time.sleep(1)

    counts = count_by_type()
    print(f"\n{'='*50}")
    print(f"{'Type':<12} {'Count':>8}  {'Target':>8}  {'Status'}")
    print(f"{'-'*50}")
    targets = {"poem": 1000, "story": 1000, "essay": 1000}
    for t, target in targets.items():
        n = counts.get(t, 0)
        status = "✓" if n >= target else f"{n/target*100:.0f}% of target"
        print(f"{t:<12} {n:>8,}  {target:>8,}  {status}")
    print(f"{'='*50}")


if __name__ == "__main__":
    all_sources = list(SOURCES.keys()) + ["johnson"]
    want = sys.argv[1:] if len(sys.argv) > 1 else all_sources
    invalid = [n for n in want if n not in all_sources]
    if invalid:
        print(f"Unknown source(s): {invalid}")
        print(f"Valid: {all_sources}")
        sys.exit(1)
    run(want)
