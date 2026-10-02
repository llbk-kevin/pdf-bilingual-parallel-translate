---
name: pdf-bilingual-parallel-translate
description: Create or revise a Chinese side-by-side bilingual PDF with the original page on the left and corresponding translation on the right. Use for PDF translation that needs source verification, preserved images and links, structured tables, resumable work, and resource/size auditing.
---

# PDF bilingual translation

## Working conventions

Generate the translation with the current session model; do not use an external machine translation service. Detect the source language, subject and page types from the document. Electronics terminology is a common case, not a scope restriction. Follow the user's explicit choices.

Use UTF-8 without BOM for every text file. When using the skill, read only the English SKILL.md; do not read the Chinese README.md. When modifying any skill document, update the other document in sync.

Keep task files outside this skill's repository. Resolve the installed skill directory before accessing scripts. Preserve a CC Switch link entry and maintain its resolved target; do not move the skill yourself.

Suggested task tree (paths are examples, not fixed machine locations):

~~~
work/bilingual/<document>/
  state.json         # Recoverable text, mapping, glossary, layout and review records
  baseline.json      # Source inspection
  audit.json         # Final mechanical audit
  build.py           # Task-specific deterministic layout builder
  renders/           # Full pages, source pages, differences; disposable
outputs/
  <stem>_双语对照翻译.pdf
  <stem>_recovery/    # State, builder and required metadata; no redundant render cache
~~~

Keep the original filename unchanged. Use relative paths within a recovery package where possible; record the external original's location and SHA-256. Record font names, hashes, permitted acquisition sources, dependencies and builder parameters so the work can be regenerated. Do not redistribute font files without permission.

## Required result

1. Completeness, accuracy, source fidelity and legibility are delivery conditions. Optimize positional correspondence next, then typographic consistency and decoration. Never omit qualifications, merge distinct content or shrink text excessively to make it fit.
2. Produce one bilingual output page for each source page, retaining the original visible area at its original scale on the left. The Chinese area defaults to the same width and height. Maintain major regions and columns; align semantic blocks rather than individual lines.
3. Translate titles, paragraphs, list items, table cells, formula explanations, captions and relevant figure labels with chapter and cross-page context. Preserve numbers, units, part numbers, variables, subscripts, superscripts, equation numbers, conditions and negation. Preserve uncertain source wording and record the uncertainty; do not silently guess.
4. Keep graphics on the left. Near the corresponding right-side position, place the figure number, translated caption and necessary translated labels, legends and axis explanations. Disambiguate by figure number, source label or position. Retain useful empty space; do not add empty colored panels, invented diagrams or a page-top caption dump.
5. Preserve real table rows, columns, headers, values and footnotes. Do not flatten tables into pipe-separated paragraphs. Repeat repeated formulas when the source repeats them. Content containing only numbers, identifiers or symbols may remain verbatim with a recorded reason.
6. Resolve overflow with line wrapping, column widths and internal spacing, then nearby blank space and local reflow, then moderate right-pane widening. Keep the source pane unchanged. If complete, readable same-page correspondence still cannot be achieved, identify the exact pages and unresolved constraint before claiming completion.
7. Preserve original image encodings and quality. Use real searchable/copyable Chinese and light vector rules. Share fonts across the document, subset them to the final glyph set and remove obsolete resources after revision. Additional fallback fonts need a specific glyph coverage purpose.
8. Regenerate revisions from the original PDF and recovery data, never by repeatedly overlaying the previous bilingual output.

Read [layout.md](references/layout.md) when designing page styles or resolving density. Read [pdf-integrity.md](references/pdf-integrity.md) before PDF composition, resource handling and structural acceptance.

## Diagnostic tools

Python 3.10+ is required. Install requirements.txt in an existing suitable environment or an isolated environment. Do not hardcode this computer's runtime path into task scripts.

~~~
python -m venv work/pdf-skill-env
<venv-python> -m pip install -r "<skill-dir>/requirements.txt"
<venv-python> "<skill-dir>/scripts/pdf_tools.py" --help
~~~

The tools inspect and render; they do not translate, create layouts, optimize PDFs or certify semantic accuracy.

| Command | Inputs | Output and use |
| --- | --- | --- |
| inspect SOURCE --out baseline.json | Original PDF | Page geometry, rotation/crop, extraction hints, links/bookmarks, unique reachable resource baseline. |
| audit SOURCE FINAL --state state.json --out audit.json | Original, final PDF; optional state | Original-pane raster/text comparison, image signatures, link/bookmark checks, new resources and size deltas. |
| render FINAL --source SOURCE --state state.json --pages all --out renders | PDF; optional source and mapping | Individual PNGs plus index.json; with a source, source and difference images. |
| check-state state.json --final --out state-check.json | Recovery JSON, referenced files | Missing translations/mapping, changed fingerprints, stale reviews and incomplete final coverage. Omit --final during work. |

Paths with spaces must be quoted. Reports/renders refuse replacement unless --overwrite is specified; input PDFs are never edited. --pages accepts all or one-based selections such as 1,3-5. Audit and render default to 144 DPI, a 40-million-pixel page limit, RGB difference tolerance 16 and changed-pixel ratio 0.001. These are comparison settings, not translation quality thresholds. Use --dpi for close checks; deliberately change --max-pixels only when memory permits. Record any relaxed comparison tolerances and inspect differences; do not hide errors by increasing thresholds.

Exit codes: 0 = requested mechanical checks completed without errors (warnings may remain); 2 = reported audit/state errors; 1 = operational failure. Render success explicitly leaves visual_review_completed false.

Read [state-and-qc.md](references/state-and-qc.md) when creating recovery data. It defines the schema, coordinates, review lifecycle and a minimal example. The source block inventory must itself be checked visually: a tool cannot discover content omitted from both the inventory and translation.

## Workflow

1. Inspect the source; save its hash and resource baseline. Render representative body, dense-table, multi-figure, formula, landscape and rotated/cropped pages as applicable. Inspect extraction against the visible original; use local OCR only when needed and verify its numbers/symbols. Choose document-specific fonts, body/caption sizes, header safe zones and restrained color.
2. Inventory every page's semantic blocks and assign stable IDs and source bounding boxes. Record source text, relevant cross-page context, table structure, figure anchors and translation status. Build a glossary from definitions and actual context. Activate vendor naming rules only for that vendor.
3. Translate a chapter/context group, then lay out representative difficult pages. Review those samples for full content, real table structure, caption position and readable size. Resolve the design before scaling up. Persist translations and layout parameters after each batch.
4. Build from the original using a task-specific script. Prefer extending the original page's visible region and adding right-side text, after normalizing or explicitly accounting for crop and rotation. Preserve interactive objects and their destinations. Run check-state during work; use render for individual pages and fix layout failures.
5. Finish all saving, font subsetting and resource cleanup. Freeze the final file, clear obsolete review records, compute its hash and run audit against the original. Explain every warning and investigate incremental images/fonts or unexplained size growth. A file-size percentage alone is not a pass/fail rule.
6. Perform three separate acceptances on that final version: (a) block-by-block translation coverage, accuracy, terminology, conditions, negation, numbers, units, tables and formulas; (b) visually open every final page, enlarging dense tables and fine captions; (c) source-pane fidelity, original images, font/resource increments, working links/bookmarks and searchable/copyable Chinese. A contact sheet is a navigation aid, not full-page inspection. Programmatic success and rendering do not replace these reviews.
7. Record actual reviewed page lists and reviewer/time, source/output/content hashes, audit path and warning resolutions. Run check-state --final. If anything changes, rebuild as needed and repeat affected semantic review plus final-file full visual/structural review; never carry stale acceptance forward.
8. Deliver the PDF and recovery data with page count, source/output sizes, absolute and percentage growth, resource deltas, validation coverage and retained uncertainties. State limitations candidly. Do not describe unviewed pages or unresolved translation as fully accepted.

For explicitly requested maintenance of this skill itself, follow AGENTS.md and [maintenance.md](references/maintenance.md). Ordinary translation jobs never enter the skill repository.
