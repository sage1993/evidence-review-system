# Codex Workflow

Use local evidence only. Run retrieval, Math Engine, approved Rule Engine rules, Track A, Track B, confidence, abstention, finalization, and rendering in order. Never replace deterministic output with prose calculations.

```bash smoke
python -c "from ansim_review.packaging.codex_bundle import CODEX_ROUTING_SECTION; assert 'never decide' in CODEX_ROUTING_SECTION.lower()"
```

For an abstention case, preserve every reason code and hand the packet to a human reviewer.
