---
name: pdf-bilingual-parallel-translate
description: Translate PDFs into Chinese side-by-side versions, preserving the original on the left and reusing its complete graphics with in-place Chinese text on the right. Use for complete translation, source verification, layout preservation, and recoverable revisions.
---

# PDF bilingual parallel translation

## Working conventions

Translate with the current session model, without external machine translation. Inspect the current PDF's language, subject, genre, audience and layout before choosing terminology. Do not infer its domain from earlier tasks. Preserve meaning, uncertainty, conditions and qualifications; do not silently correct suspected source errors.

Use UTF-8 without BOM. During ordinary use, read this English entry and only the relevant English references. For explicit skill maintenance, synchronize the Chinese README and paired references; follow AGENTS.md and [maintenance.md](references/maintenance.md). Preserve a CC Switch link and edit its resolved target. Keep document artifacts and font binaries outside this repository.

Read [naming.md](references/naming.md) for each document. Identify original/translation roles from contents, not filenames. Propose an exact before/after table before source renaming; execute after confirmation, or directly when an accepted Plan already approved that table. Preserve the original and existing outputs. Original names use confirmed identifiers when available, actual source-language titles and Chinese titles; only generated translations get the translation suffix. Apply TI-specific rules only to confirmed TI documents.

Default paths (honor user-selected destinations):

~~~text
<source-directory>/
|-- <source-stem>.pdf
|-- <source-stem>_双语左右对照翻译.pdf    # Accepted PDF only
+-- <source-stem>/
    |-- 交付说明.md
    |-- recovery/                  # State, builder, glossary and rebuilding instructions
    +-- work/                      # Drafts, extraction, renders and review evidence
~~~

Build candidates inside work/. Publish only the accepted PDF; keep sidecars inside the same-stem folder. The PDF must embed everything needed for independent reading, rendering, searching and copying. Do not delete the folder automatically; explain at delivery that deleting it loses saved editing state, evidence and resume/rebuild capability.

## Required result

Each original visible W × H page becomes exactly one 2W × H page: original at 1:1 on the left, an equally sized Chinese page on the right, including mixed sizes, crop and rotation. The right page reuses the complete original artwork, photographs, curves, table rules and formulas. Replace translatable native text locally; keep values, identifiers and mathematical notation when they need no translation. For raster or outlined labels, an explicitly bounded white cover with black Chinese text is allowed.

Keep text near its source. Adjacent verified blank space and modest per-block font fitting may be used; record the permitted box and the actual result. Do not move diagrams/table frames, enlarge the panes, truncate, omit qualifications or silently fall back to the former text-only right pane. If readable complete fitting remains unresolved, preserve the draft and identify the specific block and available tradeoff.

## Default workflow

1. **Inspect and extract.** Read [inplace.md](references/inplace.md) for the executable interface. Inspect the source, preserve its SHA-256 and resource baseline, and render representative pages. Run extract to create v3 state. Check image/outlined words, hidden OCR, columns, formulas and printed numbering against the visible pages. Follow [layout.md](references/layout.md) for semantic grouping and fitting.
2. **Translate and map.** Work from extract's stable IDs plus verified source_text, never an unrelated extraction's block indices. Merge/split blocks with retained glyph IDs and complete coverage. Assign replace, cover, preserve (with reason), or unresolved. Translate coherent passages, keep a concise glossary and record source issues with original wording and treatment. Preserve non-translatable formulas and values; use [math.md](references/math.md) when notation is present. Save authoring state after each batch.
3. **Build and inspect a trial.** Register permitted fonts and hashes. Use the default in-place builder from source plus state, never from an older bilingual PDF. It shares source image resources, removes only selected native text, writes Chinese with actual font runs and subsets fonts across the document. Unsupported interaction/clip features and overflow fail explicitly. Inspect dense tables, colored backgrounds, formula neighbors, covers and rotated pages before scaling. See [pdf-integrity.md](references/pdf-integrity.md) for preservation limits.
4. **Verify the frozen candidate.** Use its generated state for check-state, check-fonts, audit and render. Actually inspect every page and translate/check every inventoried block; renders alone do not count as review. Resolve warnings with specific evidence. Follow [state-and-qc.md](references/state-and-qc.md) for page-bound review records, invalidation and --final. Regenerate and re-review affected context after edits. Mechanical success is not semantic certification.
5. **Deliver and retain recovery.** Validate independent rebuilding from state, then publish the accepted PDF using [building.md](references/building.md). Report source/output paths and byte sizes, absolute/percentage growth, image/font/content-stream deltas, page coverage, review status and any retained issue. Never label a partial trial as an accepted full translation.

## Commands

Use a discovered Python 3.10+ interpreter with requirements.txt; development tests and the legacy example additionally need requirements-dev.txt. Prefer an existing suitable or isolated environment. Do not hardcode local runtime paths or install into shared Python merely to bypass a failing shell.

~~~text
python scripts/inplace.py extract --source SOURCE --state recovery/state.json --pages all
python scripts/inplace.py build --source SOURCE --state recovery/state.json --output work/draft.pdf --pages all
python scripts/pdf_tools.py inspect SOURCE --out work/baseline.json
python scripts/pdf_tools.py check-state work/draft.state.json --out work/state-check.json
python scripts/pdf_tools.py check-fonts work/draft.state.json --assignments work/draft.font-runs.json --out work/fonts.json
python scripts/pdf_tools.py audit SOURCE work/draft.pdf --state work/draft.state.json --out work/audit.json
python scripts/pdf_tools.py render work/draft.pdf --source SOURCE --state work/draft.state.json --pages all --out work/renders
~~~

Resolve these paths within the document working folder. Quote paths containing spaces. --pages accepts all or one-based selections such as 1,3-5; partial builds are trials and fail full-delivery coverage checks. Existing destinations require explicit --overwrite. Empty-user-password PDFs work directly; other passwords come only from a user-supplied --password-env variable, never state or logs.

Diagnostics use 144 DPI, 40 million pixels, RGB tolerance 16 and changed ratio 0.001 by default. Investigate differences instead of loosening thresholds. Exit codes are 0 for mechanical completion (warnings may remain), 2 for a diagnostic check failure and 1 for operational failure. quality_certified remains false. v1/v2 states remain readable with their original review semantics; scripts/example_build.py is an explicitly selected compatibility path only, never an automatic fallback.
