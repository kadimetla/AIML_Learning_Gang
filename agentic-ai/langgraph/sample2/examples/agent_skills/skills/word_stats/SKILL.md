---
name: word_stats
description: Compute word, character, and sentence counts for a piece of text. Use this when the user asks for exact stats/counts about a block of text, not an estimate.
---

Don't estimate word/character/sentence counts yourself -- they need to be
exact. Call run_skill_script("word_stats", text=<the text to analyze>) and
report back the numbers it returns.
