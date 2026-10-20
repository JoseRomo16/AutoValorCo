"""Listing collection: the TuCarro scrapers for cars and motorcycles, and their detail pages.

Writes to the bronze layer only. Implemented in F1.

A Fasecolda guide loader was planned here and is **out of scope**: the guide is not
reachable over plain HTTP and a subscription is ruled out by the project's zero-cost
constraint. ``valor_fasecolda`` was never a model feature either way — it would have been
leakage — only a benchmark. See ``docs/STATUS.md``.
"""
