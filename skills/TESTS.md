# Skill Verification Scenarios

Use these scenarios to check whether an agent loads and applies the correct stage-specific skill.

| Scenario | Expected skill |
|---|---|
| New regulatory PDF needs hashing and OpenDataLoader output | `preserving-and-parsing-pdfs` |
| Parser headings are flat and a diagram mixes vectors and images | `structuring-pdf-content-and-visuals` |
| OCR text has spacing errors and rule candidates need review states | `cleaning-pdf-derived-data` |
| Clean CSV must become a local `.grist` with working attachments | `building-and-exporting-grist-databases` |
| Pink image cells, blank references, and completion status must be diagnosed | `validating-pdf-database-workflows` |

## Cross-stage pressure test

Given a mixed PDF and a deadline, the agent must not skip source hashing, must not write normalized text into raw fields, must not rely only on embedded-image extraction, and must not claim completion without opening the final Grist file.
