"""Deterministic ingredient parsing, normalization, and compatibility engine.

parser.py splits raw ingredient-list text; normalizer.py resolves tokens
against the versioned rule set; compatibility.py finds pairwise
interactions; rules.py loads/validates/indexes the rule files under
``backend/rules/ingredients/``; models.py is the internal typed
representation of those files. The LLM must never compute any of this —
see ``docs/agent.md`` and ``docs/ingredients.md``.
"""
