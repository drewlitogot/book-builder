"""Prompts for a book's special sections (front matter, glossary) listed in chapter.SPECIAL.

Book Builder ships with no special sections; a book can define its own and their prompts here.
"""
from __future__ import annotations


def research_prompt(ch: dict, chapters: list[dict]) -> str:
    raise NotImplementedError("This book has no special-section research prompt defined.")


def write_prompt(ch: dict, chapters: list[dict]) -> str:
    raise NotImplementedError("This book has no special-section writing prompt defined.")
