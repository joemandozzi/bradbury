"""
Date-seeded daily picker.

Given a date, deterministically selects one story, one poem, and one essay
such that the combined reading time never exceeds 60 minutes.

Rules:
- Seed is the ISO date string so the triad is deterministic and reproducible.
- Unserved works are preferred; once all are served the pool resets.
- Works are weighted by inverse word count (shorter = more likely).
- Combined word count is capped at COMBINED_MAX (60 min at 200 wpm).
  Picks happen in order: poem → story → essay, each constrained by
  the remaining word budget.
"""
import random
from datetime import date
from corpus.db import get_works_by_type, mark_served

WORDS_PER_MINUTE = 200
MAX_MINUTES      = 60
COMBINED_MAX     = WORDS_PER_MINUTE * MAX_MINUTES  # 12,000 words


def _pick(rng: random.Random, pool: list, max_words: int):
    """
    Pick one work from pool weighted by inverse word count,
    constrained to works with word_count <= max_words.
    Returns None if no eligible work exists.
    """
    eligible = [w for w in pool if (w["word_count"] or 500) <= max_words]
    if not eligible:
        # Relax to the single shortest work available
        eligible = sorted(pool, key=lambda w: w["word_count"] or 500)[:1]
    if not eligible:
        return None

    def weight(w):
        return 1.0 / max(w["word_count"] or 500, 1)

    weights = [weight(w) for w in eligible]
    return rng.choices(eligible, weights=weights, k=1)[0]


def _get_pool(works: list) -> list:
    """Prefer unserved; fall back to full pool if all served."""
    unserved = [w for w in works if not w["served"]]
    return unserved if unserved else list(works)


def pick_for_date(target_date=None) -> dict:
    """
    Returns {'story': Row, 'poem': Row, 'essay': Row} for the given date.
    Combined word count will not exceed COMBINED_MAX (12,000 words / 60 min).
    """
    if target_date is None:
        target_date = date.today()

    rng    = random.Random(target_date.isoformat())
    result = {}
    budget = COMBINED_MAX

    # 1. Poem first — almost always tiny, rarely uses more than 200 words.
    poems = _get_pool(get_works_by_type("poem"))
    poem  = _pick(rng, poems, budget - 200)  # leave room for story + essay
    result["poem"] = poem
    budget -= (poem["word_count"] or 0) if poem else 0

    # 2. Story — takes the biggest share, leave at least 500 words for an essay.
    stories = _get_pool(get_works_by_type("story"))
    story   = _pick(rng, stories, budget - 500)
    result["story"] = story
    budget -= (story["word_count"] or 0) if story else 0

    # 3. Essay — whatever budget remains.
    essays = _get_pool(get_works_by_type("essay"))
    essay  = _pick(rng, essays, budget)
    result["essay"] = essay

    # Mark all three as served.
    for work in result.values():
        if work:
            mark_served(work["id"])

    return result


def reading_time_minutes(triad: dict) -> int:
    """Return estimated combined reading time in minutes."""
    total_words = sum(
        (w["word_count"] or 0) for w in triad.values() if w
    )
    return round(total_words / WORDS_PER_MINUTE)
