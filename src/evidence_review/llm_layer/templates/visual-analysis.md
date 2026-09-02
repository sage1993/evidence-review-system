# Visual Analysis Instructions

You are producing **case-specific visual observations only** for an Evidence Review System formal review.

Read `visual-analysis-bundle.json`. For every relevant page, open the exact local raster named by `asset_path` and inspect the image itself. `asset_path` is relative to the review workspace; resolve it from that workspace and do not substitute another file. Do not infer visual facts solely from the question text, filenames, QuestionPlan facts, or prior knowledge.

Write only `visual-analysis-output.json` with this structure:

```json
{
  "format": "evidence-review/visual-analysis-output",
  "version": 1,
  "visual_analysis_id": "<exact bundle id>",
  "observations": [
    {
      "attachment_id": "<exact attachment id>",
      "source_sha256": "<exact source hash>",
      "page": 1,
      "issue_ids": ["<existing issue id>"],
      "candidate_type": "<neutral semantic visual feature type>",
      "geometry": {
        "type": "POINT|BBOX|LINESTRING|POLYGON",
        "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
        "coordinates": []
      },
      "raw_value": null,
      "normalized_candidate": null
    }
  ]
}
```

Rules:

- Use only attachment IDs, source hashes, pages, issue IDs, coordinate systems and page bounds from the bundle.
- Coordinates are pixels in the displayed raster, origin at the top-left.
- Geometry must match its declared type. A POINT is `[x, y]`; a BBOX is `[left, top, right, bottom]`; LINESTRING and POLYGON coordinates are arrays of `[x, y]` points. For a POLYGON, the final point must exactly equal the first point.
- `raw_value` must be a JSON string or null.
- `normalized_candidate` must be a JSON string or null.
- `raw_value` and `normalized_candidate` must never be an object, array, number, or boolean.
- Create an observation only for something actually visible on the referenced page.
- **Create semantic reviewable observations, not OCR token dumps.** Do not emit standalone fragments such as `3F`, `101동`, isolated dimension numbers, or individual room labels when adjacent visible elements jointly describe one reviewable fact.
- When several visible labels/dimensions belong to one coherent fact, emit one observation using a tight enclosing BBOX/POLYGON and summarize the visible content concisely in `normalized_candidate`. Examples include one unit-space program, one area schedule, one set of related levels/elevations, one set of road/setback dimensions, or one building-identification group.
- Keep observations separate when they concern independent issues, independent locations, or facts that would be reviewed separately.
- Use a tight BBOX/POLYGON/LINESTRING/POINT around the complete semantic feature. Do not create placeholder geometry.
- **Geometry is source evidence, not a navigation hint.** The reviewer UI will draw and focus this geometry as the visible evidence region, so coordinates must correspond to the actual marks that justify the observation.
- **Every boundary of a BBOX or POLYGON must be justified by visible content that belongs to the observation.** Before writing an observation, inspect the proposed geometry and shrink any side that extends beyond the supporting labels, lines, symbols, table cells, or drawing region.
- **Do not include large blank areas, decorative frames, unrelated notes, or nearby but independent content merely to make a convenient rectangle.** A large central rectangle that mostly encloses empty space is invalid evidence geometry.
- For localized text such as a **project title or project-identification text**, bound the visible title/identification marks themselves with only a small visual margin. Do not extend the geometry into an unrelated stamp, reception note, blank title-sheet field, logo, or page center.
- A broad BBOX is appropriate only for a genuinely **page-scale observation** whose `normalized_candidate` explicitly describes the whole bounded region, such as an entire floor-plan field, a full schedule table, or a site-plan region. Do not use page-scale geometry for a localized label or title.
- If one semantic fact is supported by spatially separate regions that cannot be enclosed tightly without including substantial unrelated content, emit separate observations for the separate regions instead of one oversized enclosing BBOX.
- Before finalizing output, perform a geometry self-check for every observation: (1) the geometry contains the described evidence, (2) unrelated content is minimized, (3) a localized feature is not represented by page-scale geometry, and (4) the geometry would be understandable if shown alone as a reviewer highlight.
- `raw_value` may reproduce visible text or visible labels. If text is unreadable, use null rather than guessing.
- `normalized_candidate` may normalize or compact **only actually visible values**; it must not add a value that is not visible.
- `candidate_type` describes a neutral semantic visual feature, not a legal conclusion.
- An empty `observations` array is valid when the requested visual fact cannot be established from the supplied pages.

Forbidden:

- legal compliance/noncompliance conclusions
- rule status, calculation result, confidence, final decision, answer, conclusion, recommendation
- treating a statement from the user's question as if it had been seen in the image
- inventing dimensions, room uses, boundaries, entrances, equipment, labels or page content
- returning a list of OCR words/numbers merely because they are readable when they do not form independently reviewable facts
- citing a different attachment, source hash, page or issue
- coordinates outside the page bounds

Do not write explanatory prose outside the JSON output.
