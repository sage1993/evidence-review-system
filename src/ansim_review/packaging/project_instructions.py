"""Canonical ChatGPT web project instructions."""
from __future__ import annotations


def render_project_instructions() -> str:
    """Return stable offline-review instructions."""
    return """# ChatGPT Web Offline Evidence Review

1. Run `python bootstrap.py --self-test`.
2. Use only local evidence and approved manifests.
3. Execute retrieval, Math Engine, Rule Engine, Track A, Track B, confidence, abstention, and finalization in that order.
4. Do not call APIs or remote search from runtime code.
5. Do not calculate or alter engine statuses in prose.
6. Keep `human_decision` null; the human reviewer records a separate decision.
"""
