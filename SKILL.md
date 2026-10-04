---
name: pdf-bilingual-parallel-translate
description: Translate PDFs into Chinese side-by-side versions, preserving the original on the left and providing corresponding translations on the right. Use for tasks requiring complete translation, source verification, layout preservation, and later revision.
---

# PDF bilingual parallel translation

## Working conventions

Translate with the current session model, without external machine translation. Before every translation, examine the current PDF to identify its language, subject, genre, intended audience and layout; use these findings to choose terminology, expression and applicable checks. Do not infer the subject from previous translation tasks. Keep uncertain classifications tentative. Follow explicit user choices.

Use UTF-8 without BOM. When using the skill, read only the English SKILL.md and relevant English references; do not read the Chinese README.md. For explicit skill maintenance, synchronize both languages and follow AGENTS.md and [maintenance.md](references/maintenance.md). Resolve the installed directory; preserve a CC Switch link and maintain its target without moving it yourself. Keep task files outside this repository; do not embed account balances or temporary quota policies in the skill.

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

Prefer relative recovery paths. Record the external original's SHA-256, font names/hashes/acquisition sources, dependencies and builder parameters. State is the authoritative translation/layout input, not an appendix to hardcoded Python translations.

## Required result

1. Completeness, accuracy, source fidelity and legibility are delivery conditions; optimize spatial correspondence next, then typography. Never omit qualifications, merge distinct meanings or excessively shrink text to fit.
2. Map every source page to one output page. Keep its visible original at 1:1 on the left; default the Chinese pane to the same dimensions. Align semantic blocks and columns rather than individual lines.
3. Preserve the source's meaning, tone, information structure and uncertainty. Never silently correct the source or present guesses as facts.
4. Preserve original image encodings and quality. Chinese text must remain searchable and copyable; use light vectors and avoid introducing redundant resources.

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

1. Assess the current document as specified in the working conventions; identify roles, naming and paths. Inspect the source and preserve its hash/resource baseline. Render representative pages and verify extraction/OCR and any numbers/symbols present. Read [layout.md](references/layout.md) and choose document-specific pane dimensions, fonts, sizes, colors and safe margins.
2. Read [state-and-qc.md](references/state-and-qc.md) before creating recovery state. Inventory the content actually present: headings, paragraphs, lists, and any table cells, formulas, captions or meaningful figure labels. Check against the visible original; preserve source-fragment mappings, reading order, cross-page dependencies and contextual terminology. Distinguish image-only labels, duplicate extraction and invisible text. Translate coherent passages or context groups. Record source issues with page, block, original wording, concern and treatment; optional suggested corrections need evidence. Persist state after every batch.
3. Read [pdf-integrity.md](references/pdf-integrity.md) before composition. Build from the original and state, never by overlaying an old bilingual PDF. Read translations, complete table cells and layout from state without overwriting authoring edits. Copy the example and its helper into task recovery before adapting them. Share fonts across the document, assign fallback fonts to specific missing glyphs, check glyphs during construction and run check-fonts on actual draw-time runs. Preserve genuine tables and repeated equations where present; read [math.md](references/math.md) for mathematical notation and preserve readable structure over ASCII substitutes.

   Where graphics are present, keep them on the left and place corresponding captions and keyed label/legend/axis translations nearby on the right. Disambiguate with figure numbers, source labels or precise positions. Keep useful blank space; avoid empty colored panels, invented diagrams and page-top caption dumps. Place short notes beside meaning-affecting source contradictions or uncertainties.

   Trial representative pages before scaling. Improve wrapping, column widths and spacing, then nearby reflow, then moderate right-pane widening, preserving the source pane. Record exact unresolved pages if full readable same-page correspondence remains impossible. Check draft state, render and inspect samples, and fix overflow plus any table geometry or mathematical notation problems. Keep clearly named drafts under work/ as defined above and save exact batch/queue checkpoints.
4. Verify recovery in an independent copy: rebuild, edit one existing translated block and, if tables are present, one table cell; confirm output changes while authoring edits survive. Do not add a table just to perform this check. Repeated generation must not accumulate resources. Byte-identical rebuilding is useful; explain metadata-only differences when applicable.
5. Finish saving, font subsetting, lossless content compression and resource cleanup. Freeze/hash the candidate and audit it. Investigate warnings by page/resource and preserve original reports; demonstrated tool defects need explicitly bound alternative evidence, not edited pass flags.
6. Perform separate translation, visual and structural acceptance. Check completeness, meaning, tone, negation, conditions, qualifications and proper names; where present, also verify numbers, units, signs, comparison operators, proportional/inverse relationships, subscripts/superscripts, table correspondence and repeated equations. Initially view every full page, inspect final rendered glyphs and enlarge dense details; contact sheets only aid navigation. Apply the PDF integrity reference to structural acceptance. After repair, rerender the whole book and repeat structure checks. Re-view changed pages; reuse prior viewed pages only with matching pixels, renderer settings, text/layout and semantic dependencies plus traceable original records. Otherwise view again.
7. Record only actual reviews: page, viewer/time/evidence, PDF/render/content hashes and reuse reason. check-state --final validates records, not whether the model understood the page. Rendering or mechanical success never proves accuracy.
8. Deliver PDF/recovery with page count, original/output sizes, absolute/percentage growth, resource deltas, coverage and full retained-issue notes. State incomplete work and exact unresolved pages honestly. Before an approved recovery relocation, follow the path-only migration procedure in [state-and-qc.md](references/state-and-qc.md); preserve old acceptance and a verified migration chain, never replace old hashes and call it a new review.
