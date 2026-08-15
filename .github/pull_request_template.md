## Summary

Describe the problem and the smallest implemented solution.

## Related issues

Closes #

## Architecture / trust-boundary impact

- [ ] No source/evidence authority changes
- [ ] No network/offline-boundary changes
- [ ] No human-decision authority changes
- [ ] No release/package integrity changes

If any box above is not checked, explain the change and why the new behavior remains fail-closed.

## Validation

List exact commands actually executed and their results. Use `NOT_RUN` for anything not executed.

```text
pytest:
Ruff:
mypy:
compileall:
documentation integrity:
wheel/runtime smoke:
manual browser QA:
```

## Data safety

- [ ] No proprietary/customer PDFs or parser outputs are committed.
- [ ] No user evidence databases/page-image caches/human decisions are committed.
- [ ] No credentials, tokens, private URLs, or private keys are committed.

## Review notes

Call out migrations, compatibility behavior, performance tradeoffs, and manual reviewer steps.
