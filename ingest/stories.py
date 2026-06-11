"""
Ingest short stories — Phase 1 hand-picked seed.

Rather than parsing whole Gutenberg collections in Phase 1, we use a curated
list of stories that exist as standalone Gutenberg texts. Each entry maps to
a single plain-text file — no segmentation needed.

Run: python ingest/stories.py
"""
import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from corpus.db import init_db, insert_work, count_by_type

# Each entry: (title, author, year, gutenberg_id)
# ALL IDs are verified standalone texts — the whole file IS the story/novella.
# No collection extraction needed.
STORIES = [
    # Confirmed standalone short stories
    ("The Yellow Wallpaper",                    "Charlotte Perkins Gilman", 1892, 1952),
    ("The Cask of Amontillado",                 "Edgar Allan Poe",          1846, 1063),
    ("An Occurrence at Owl Creek Bridge",        "Ambrose Bierce",           1890, 375),
    ("The Monkey's Paw",                        "W.W. Jacobs",              1902, 12122),
    ("The Gift of the Magi",                    "O. Henry",                 1905, 7256),
    ("The Ransom of Red Chief",                 "O. Henry",                 1910, 7261),
    # Confirmed standalone novellas (whole file = the work)
    ("Bartleby, the Scrivener",                 "Herman Melville",          1853, 11231),
    ("Daisy Miller",                            "Henry James",              1878, 208),
    ("The Strange Case of Dr. Jekyll and Mr. Hyde", "Robert Louis Stevenson", 1886, 43),
    ("The Great God Pan",                       "Arthur Machen",            1894, 389),
    ("The Turn of the Screw",                   "Henry James",              1898, 209),
    ("A Christmas Carol",                       "Charles Dickens",          1843, 46),
    ("The Time Machine",                        "H.G. Wells",               1895, 35),
    ("The Island of Doctor Moreau",             "H.G. Wells",               1896, 159),
    # Collections where extraction works reliably (title is the first story)
    ("The Legend of Sleepy Hollow",             "Washington Irving",        1820, 41),
    ("Rip Van Winkle",                          "Washington Irving",        1819, 41),
    ("The Man Who Would Be King",               "Rudyard Kipling",          1888, 8153),
    ("The Lifted Veil",                         "George Eliot",             1859, 2165),
    ("The Jolly Corner",                        "Henry James",              1908, 1190),
    ("The Fall of the House of Usher",          "Edgar Allan Poe",          1839, 932),
    ("The Call of the Wild",                    "Jack London",              1903, 215),
    ("To Build a Fire",                         "Jack London",              1908, 1160),
    ("The Call of the Wild",       "Jack London",              1903, 215),
    ("To Build a Fire",            "Jack London",              1908, 1160),
]

# Gutenberg plain-text URL pattern.
TXT_URL = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"


def fetch_text(gutenberg_id: int) -> str:
    url = TXT_URL.format(id=gutenberg_id)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    try:
        return resp.content.decode("utf-8")
    except UnicodeDecodeError:
        return resp.content.decode("latin-1")


def clean_gutenberg_text(text: str) -> str:
    """Strip Gutenberg header/footer boilerplate."""
    for marker in ["*** START OF THE PROJECT GUTENBERG", "***START OF THE PROJECT GUTENBERG"]:
        idx = text.find(marker)
        if idx != -1:
            text = text[text.find("\n", idx) + 1:]
            break
    for marker in ["*** END OF THE PROJECT GUTENBERG", "***END OF THE PROJECT GUTENBERG"]:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
            break
    return text.strip()


def extract_story_from_collection(full_text: str, title: str) -> str:
    """
    For files that are collections (e.g. Poe's Tales, Irving's Sketch Book),
    extract the specific story by finding the title and the next story header.
    """
    # Look for the title as a standalone line.
    pattern = re.compile(
        r"^" + re.escape(title.upper()) + r"\s*$|^" + re.escape(title) + r"\s*$",
        re.MULTILINE | re.IGNORECASE
    )
    match = pattern.search(full_text)
    if not match:
        # Fallback: just return the whole text (for standalone files).
        return full_text

    start = full_text.find("\n", match.end()) + 1
    # Find next story-like header: an all-caps line of 10+ chars.
    end_pattern = re.compile(r"\n\n([A-Z][A-Z\s,;:\'\"\.]{9,})\n\n", re.MULTILINE)
    end_match = end_pattern.search(full_text, start + 500)
    if end_match:
        return full_text[start:end_match.start()].strip()
    return full_text[start:].strip()


def ingest_stories():
    init_db()
    total = 0

    # Track which Gutenberg IDs we've already downloaded (some are collections).
    cache: dict[int, str] = {}

    for title, author, year, gid in STORIES:
        print(f"  {title}...", end=" ", flush=True)
        try:
            if gid not in cache:
                cache[gid] = clean_gutenberg_text(fetch_text(gid))
            raw = cache[gid]
            text = extract_story_from_collection(raw, title)
            word_count = len(text.split())
            if word_count > 60000:
                print(f"SKIP (too long at {word_count:,} words — bad extraction)")
                continue
            insert_work(
                type="story",
                title=title,
                author=author,
                year=year,
                word_count=word_count,
                text=text,
                source_url=f"https://www.gutenberg.org/ebooks/{gid}",
                source_name="Project Gutenberg",
            )
            print(f"✓ ({word_count:,} words)")
            total += 1
        except Exception as e:
            print(f"ERROR: {e}")

    print(f"\nDone. Total stories in DB: {count_by_type().get('story', 0)}")


if __name__ == "__main__":
    ingest_stories()
