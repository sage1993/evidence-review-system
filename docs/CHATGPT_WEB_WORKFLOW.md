# ChatGPT Web Workflow

Build or upload the reproducible offline ZIP. The runtime performs no API calls and requires no package installation. Source PDFs are excluded by default; evidence records retain source hashes and coordinates.

```bash smoke
python -c "from ansim_review.packaging.project_instructions import render_project_instructions; assert 'human_decision' in render_project_instructions()"
```

A ready case and an abstention case use the same deterministic sequence. The final machine packet never contains a selected human decision.
