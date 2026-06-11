#!/usr/bin/env python3
"""
figma_sync.py — apply design tokens from figma_tokens.json → static/style.css

FULL PIPELINE:
  1. Ask Claude Code to "export Figma tokens" — it calls use_figma to read
     the Tokens variable collection and writes figma_tokens.json.
  2. python figma_sync.py          ← you are here
  3. python build.py               ← rebuild site with new styles

figma_tokens.json format (written by Claude's use_figma export step):
  {
    "light": { "--color-bg": "#f8f7f4", "--color-text": "#1a1a1a", ... },
    "dark":  { "--color-bg": "#161409", "--color-text": "#ede8df", ... }
  }

Usage:
    python figma_sync.py [--dry-run]
"""
import json, re, sys
from pathlib import Path

CSS_PATH    = Path(__file__).parent / "static" / "style.css"
TOKENS_PATH = Path(__file__).parent / "figma_tokens.json"
DRY_RUN     = "--dry-run" in sys.argv


def patch_block(css: str, block_re: str, tokens: dict) -> str:
    def replacer(match):
        block = match.group(0)
        for name, value in tokens.items():
            block = re.sub(
                rf"({re.escape(name)}:\s*)[^;]+",
                rf"\g<1>{value}",
                block,
            )
        return block
    return re.sub(block_re, replacer, css, flags=re.DOTALL)


def main():
    if not TOKENS_PATH.exists():
        sys.exit(
            "figma_tokens.json not found.\n"
            "Ask Claude Code to 'export Figma tokens' first — it will create that file."
        )

    tokens = json.loads(TOKENS_PATH.read_text())
    light  = tokens.get("light", {})
    dark   = tokens.get("dark", {})

    if not light:
        sys.exit("figma_tokens.json has no 'light' tokens.")

    css     = CSS_PATH.read_text()
    updated = css

    updated = patch_block(updated, r":root\s*\{[^}]*\}", light)

    if dark:
        updated = patch_block(
            updated,
            r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{[^}]*:root[^}]*\{[^}]*\}[^}]*\}",
            dark,
        )

    if updated == css:
        print("CSS already matches tokens — no changes.")
        return

    if DRY_RUN:
        print("--- dry run: would write the following ---")
        print(updated)
        return

    CSS_PATH.write_text(updated)
    print(f"Updated {CSS_PATH}")
    print("Run `python build.py` to rebuild the site.")


if __name__ == "__main__":
    main()
