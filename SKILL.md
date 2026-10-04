---
name: pdf-bilingual-parallel-translate
description: Translate PDFs into Chinese side-by-side versions, preserving the original on the left and providing corresponding translations on the right. Use for tasks requiring complete translation, source verification, layout preservation, and later revision.
---

# PDF bilingual parallel translation

## Working conventions

Translate with the current session model, without external machine translation. Before every translation, examine the current PDF to identify its language, subject, genre, intended audience and layout; use these findings to choose terminology, expression and applicable checks. Do not infer the subject from previous translation tasks. Keep uncertain classifications tentative. Follow explicit user choices.

Use UTF-8 without BOM. When using the skill, read only the English SKILL.md and relevant English references; do not read the Chinese README.md. When modifying documents, synchronize both languages. Keep task files outside this repository. Resolve the installed directory; preserve a CC Switch link and maintain its target without moving it yourself.

Default task layout (honor user-specified destinations):

~~~text
<source-directory>/
|-- <source-stem>.pdf
+-- <source-stem>/
    |-- <delivery-name>.pdf       # Accepted output only
    |-- 交付说明.md
    |-- recovery/                # State, builder, glossary and regeneration instructions
    +-- work/                    # Drafts, extraction, renders, audits and checkpoints
~~~

Identify document roles from content, not Chinese filenames or translation suffixes. Present an exact before/after table for source renaming; in normal mode rename after confirmation, while an accepted Plan's table requires no second confirmation. Never overwrite the source or a colliding target; preserve old translations unless deletion was explicitly requested. Only after confirming that the current document is from TI, read and apply [naming.md](references/naming.md).

Prefer relative recovery paths. Record the external original's SHA-256, font names/hashes/acquisition sources, dependencies and builder parameters. State is the authoritative translation/layout input, not an appendix to hardcoded Python translations. Copy the example and its helper into task recovery before adapting it.

## Required result

1. Completeness, accuracy, source fidelity and legibility are delivery conditions; optimize spatial correspondence next, then typography. Never omit qualifications, merge distinct meanings or excessively shrink text to fit.
2. Map every source page to one output page. Keep its visible original at 1:1 on the left; default the Chinese pane to the same dimensions. Align semantic blocks and columns rather than individual lines.
3. Inventory the content actually present: headings, paragraphs, lists, and any table cells, formulas, captions or meaningful figure labels. Preserve reading order and cross-page context. Join extraction fragments with source mappings; distinguish image-only labels, duplicate extraction and invisible text. Check inventory against the visible original.
4. Check completeness, meaning, tone, negation, conditions, qualifications and proper names. Where present, also verify numbers, units, signs, comparison operators, proportional/inverse relationships and subscripts/superscripts; preserve repeated equations and genuine table structure. See [layout.md](references/layout.md). Read [math.md](references/math.md) when the source contains mathematical notation, preserving readable structure over ASCII substitutes.
5. Where graphics are present, keep them on the left. Place corresponding captions and keyed label/legend/axis translations nearby on the right. Disambiguate with figure numbers, source labels or precise positions. Useful blank space is valid; no empty colored panels, invented diagrams or page-top caption dumps.
6. Fit by improving wrapping, column widths and spacing, then nearby reflow, then moderate right-pane widening. Preserve the source pane. Report exact unresolved pages if full readable same-page correspondence remains impossible.
7. Preserve uncertain source meaning. Record page, block, original wording, concern and treatment; optional suggested corrections need evidence. Put short notes beside meaning-affecting contradictions and full issues in recovery/delivery notes. Never silently correct a source or present guesses as facts.
8. Reuse original image encodings/quality. Add searchable/copyable Chinese and light vectors; share and subset fonts across the document. Assign fallback fonts to specific missing glyphs. Check the font actually used for each run, then inspect final rendered glyphs.
9. Regenerate from original plus state, never by overlaying an old bilingual PDF. Builders must read translations, complete table cells and layout from state without overwriting authoring edits. Keep clearly named drafts under work/.

Read [pdf-integrity.md](references/pdf-integrity.md) before composition/structural acceptance and [state-and-qc.md](references/state-and-qc.md) before creating or migrating recovery data.

## Tools and build interface

Use Python 3.10+ and requirements.txt for diagnostics; the optional example also needs requirements-dev.txt. Discover an available interpreter first. Prefer a suitable existing or isolated environment; do not install into shared Python merely to bypass a failing shell. Call the interpreter directly when needed, without hardcoding machine runtime paths into the skill.

~~~text
python -m venv work/pdf-skill-env
<venv-python> -m pip install -r "<skill-dir>/requirements-dev.txt"
<venv-python> "<skill-dir>/scripts/pdf_tools.py" --help
~~~

| Entry | Inputs | Output and purpose |
| --- | --- | --- |
| inspect SOURCE --out baseline.json | Original | Geometry, extraction, links/bookmarks and reachable resources. |
| audit SOURCE FINAL --state state.json --out audit.json | Original, final, optional mapping | Uniform-scale original comparison, resources, links, size and content-stream findings. |
| render FINAL --source SOURCE --state state.json --pages all --out renders | Final, optional original/mapping | PNGs and immutable index with file/pixel/content/settings hashes; never records viewing. |
| check-fonts state.json --assignments final.font-runs.json --out fonts.json | State and actual draw-time runs | Assigned-font coverage, missing glyphs, fallback use and unverified fonts. |
| check-state state.json --final --out state-check.json | State and referenced evidence | Consistency, fingerprints, coverage and review records; omit --final during work. |
| scripts/example_build.py --source SOURCE --state state.json --output work/draft.pdf | Explicit boxes, registered fonts and complete state | Deterministic PDF, draft.state.json and draft.font-runs.json; input state is read-only. |

The example is a building pattern, not a universal layout engine. It requires unrotated, uncropped, zero-origin pages and fails on unsupported geometry/overflow. Adapt deliberately; [building.md](references/building.md) explains fonts, tables and independent-copy rebuilding.

Quote paths with spaces. Reports/renders and the example refuse overwrite without --overwrite; originals remain protected. --pages accepts all or one-based selections such as 1,3-5. Default comparisons use 144 DPI, 40 million pixels, RGB tolerance 16 and changed ratio 0.001, not translation-quality thresholds. Investigate differences instead of relaxing thresholds to hide them. Empty-user-password PDFs work directly; required passwords use --password-env with an explicitly supplied environment variable, never saved or logged.

Diagnostic exit codes: 0 = mechanical completion without errors (warnings may remain); 2 = reported check failure; 1 = operational failure. ready_for_delivery is a compatibility consistency field, not semantic certification; quality_certified stays false. Version 1 states are labeled legacy attestations, not silently upgraded to version 2 evidence.

## Workflow

1. Examine the current PDF's language, subject, genre, intended audience and layout. Choose terminology, expression and checks from that document, leaving uncertain classifications tentative. Identify roles, naming and paths; inspect source and preserve its hash/resource baseline. Render representative pages, verify extraction/OCR and any numbers/symbols present, then choose document-specific fonts, sizes, colors and safe margins.
2. Inventory blocks in reading order with cross-page dependencies and contextual terminology. Translate a coherent passage or context group; trial representative pages before scaling. Persist state after every batch.
3. Build from source/state, check glyphs during construction and run check-fonts on actual draw-time runs. Check draft state; render samples and fix overflow plus any table geometry or mathematical notation present. Save exact batch/queue checkpoints without embedding account balances or temporary quota policies in the skill.
4. Verify recovery in an independent copy: rebuild, edit one existing translated block and, if tables are present, one table cell; confirm output changes while authoring edits survive. Do not add a table just to perform this check. Repeated generation must not accumulate resources. Byte-identical rebuilding is useful; explain metadata-only differences when applicable.
5. Finish saving, font subsetting, lossless content compression and resource cleanup. Freeze/hash the candidate and audit it. Investigate warnings by page/resource and preserve original reports; demonstrated tool defects need explicitly bound alternative evidence, not edited pass flags.
6. Perform separate translation, visual and structural acceptance. Initially view every full page and enlarge dense details; contact sheets only aid navigation. After repair, rerender the whole book and repeat structure checks. Re-view changed pages; reuse prior viewed pages only with matching pixels, renderer settings, text/layout and semantic dependencies plus traceable original records. Otherwise view again.
7. Record only actual reviews: page, viewer/time/evidence, PDF/render/content hashes and reuse reason. check-state --final validates records, not whether the model understood the page. Rendering or mechanical success never proves accuracy.
8. Deliver PDF/recovery with page count, original/output sizes, absolute/percentage growth, resource deltas, coverage and retained issues. State incomplete work honestly. Path-only renames preserve old acceptance and a verified migration chain; do not replace old hashes and call it a new review.

Explicit skill maintenance follows AGENTS.md and [maintenance.md](references/maintenance.md). Ordinary translation files never enter this repository.
