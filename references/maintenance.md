# Skill maintenance and verified scope

This reference is for skill maintenance. Document names and subjects in historical validation records describe past checks only; do not use them to infer a new translation task's domain or preferred style.

## Repository and installation

The maintained repository is llbk-kevin/pdf-bilingual-parallel-translate, private, with main as its default branch. The global entry is <CODEX_HOME>/skills/pdf-bilingual-parallel-translate. A newly created ordinary directory stays there until CC Switch manages it. Do not manually migrate it.

Before edits, inspect whether the entry is a link and resolve its target. Modify the actual directory. Afterwards verify that the same link still points to the same target and the entry reads the updated content. If no link exists, maintain the ordinary directory. Report a broken link or diverged copies before attempting replacement.

## Maintenance workflow

For an explicit request to change this skill, synchronize SKILL.md and README.md, plus each changed English reference and its .zh-CN.md counterpart. Keep commands, schema identifiers and examples equivalent. Read the English entry during normal skill use; Chinese documents support user review and maintenance.

Install requirements-dev.txt in a suitable Python environment and run, from the actual skill directory:

~~~
python -m unittest discover -s tests -v
python scripts/pdf_tools.py --help
~~~

The integration tests generate small PDFs in temporary directories using ReportLab and pypdf; they do not require the desktop documents or licensed font files. Runtime tools require pypdf, pypdfium2, Pillow and fonttools. Development and the optional builder additionally use ReportLab. First-release verified versions: pypdf 6.10.0, pypdfium2 5.13.0, Pillow 12.3.0, ReportLab 4.4.9, on Windows. The requirements files allow compatible minor updates; rerun relevant tests after dependency updates. Inventory intentionally uses pypdf 6.x encoded-stream internals, so a major upgrade requires review.

Run the installed skill-creator validator if available, and inspect UTF-8/BOM status, Markdown links and UI metadata. Before commit, review git diff and tracked files. Exclude task inputs, outputs, state, render caches, font binaries and secrets. Use Conventional Commits with an English type/scope, Chinese description and a multiline Chinese body for substantive changes. Keep Chinese comments for .gitignore groups.

Commit and push validated changes to origin/main as the selected maintenance policy. Never force-push or discard unrelated work. If remote state has advanced, fetch and integrate only understood changes, then validate the result. If authentication or push fails, preserve local commits and report the exact remaining step. Ordinary PDF translation does not modify or synchronize this repository.

## First-release validation

18 synthetic integration tests cover nested/shared image resources; original duplication versus newly introduced copies; duplicate font streams; changed Decode semantics; lossless palette recompression and numeric representation; rotation/crop; source raster corruption; removed links/bookmarks; table shape and missing translations; missing figure anchors; caption displacement and pipe-table hints; source/output/builder/layout-input fingerprint changes; stale/incomplete reviews; render indices; overwrite protection; and deterministic read-only audits.

Three original/previous-translation pairs totaling 74 pages were locally audited: NSI826x (32), NSI8608 (20), and a flyback presentation (22). All original panes passed the raster comparison, image byte increments were zero, and existing duplicate resources were not mislabeled as newly introduced. Warnings identified candidate table flattening, caption displacement, small Chinese and changed links. These are diagnostic findings, not semantic certification of the old translations.

A separately generated seven-page local sample covered the NSI826x double-column first page, parameter table, multi-figure page and repeated-formula page; an NSI8608 circuit explanation page; and flyback diagram/landscape-table pages. All seven pages were individually inspected, with dense tables enlarged. The sample reused original images, introduced no bitmap bytes, retained real table cells and repeated equations, and used shared subset fonts. Rebuilding produced the same PDF hash. Source sample: 1,742,417 bytes; bilingual sample: 2,125,713 bytes; image/Form delta: zero; added font streams: 162,063 encoded bytes. Sample PDFs, task builder, translations and recovery data are local deliverables, not repository fixtures.

## Naming, recovery and evidence upgrade

The initial migration of requirements reduced “do not automatically rename the original” to preserving its filename, losing identification, proposal, confirmation and execution rules. This was an incomplete requirements migration. The naming reference restores the whole workflow and the user-selected convention that TI English originals and translated outputs share a basename in separate directories.

35 synthetic tests now cover the original checks plus TI formatting/omitted IDs, title normalization, duplicate suffix prevention, same-name source/output separation, assigned-font missing glyphs and fallback, state-driven full table cells, overflow, external input retention, deterministic rebuilds, actual render evidence, strict reuse/context invalidation, path-only relocation, fixed-scale fractional geometry, empty/explicit passwords, caption roles and uncompressed streams. Test fonts are generated procedurally; their shapes are fixtures, not a visual typography benchmark.

Local regression audited Sensors (15), Moog (40) and TDK (107), totaling 162 pages: all original panes had zero changed pixels with the uniform-matrix renderer. Moog’s former dimension-dependent sampling mismatch disappeared without loosening tolerances. TDK’s empty user password worked through the standard reader; 103 small marginal-text findings were distinguished from three footnote-related small-text warnings. Those warnings still need documented human interpretation. The historical benchmark font was independently confirmed to lack U+2243 and U+2095; declared assigned-font checking now catches such absence even when extraction succeeds. This does not replace final visual inspection.

The task-local migration records and independent rebuild evidence stay outside the skill repository. Existing version 1 packages retain their original review history; a rename is not an invented version 2 acceptance. Do not claim all previous translations were re-reviewed during this maintenance.

## Equal panes and confirmed page numbering

42 synthetic tests cover the previous behavior plus equal-pane construction on mixed/fractional pages, rejection of wider/narrower legacy widths, output geometry and source placement errors with unchanged 0.1 pt tolerance, explicit original/physical page labels, unnumbered covers, actual page-label font runs and invalidation. Rotation/crop fixtures also assert equal visible panes. The optional numbering fields do not identify printed labels automatically.

Generate visual fixtures outside the repository with tests/generate_layout_samples.py --out <task-dir>/samples --font <permitted-Chinese-TrueType-font>, adding --face-index if needed. The font and outputs stay local. Three documents totaling seven pages cover an unnumbered cover plus iv/A-3 labels, wholly unnumbered pages including a blank page, and a locally reduced table with nearby margin use. All seven pages and the enlarged table were actually inspected; source panes were pixel-identical, image/Form byte deltas were zero, font checks and state checks passed, and repeated builds were byte-identical. Keeping the table at the 11.5 pt body size overflowed; 8.5 pt fit while body text stayed 11.5 pt. These are small fixtures, not evidence that all future layouts fit.

Read-only regression on Sensors (15), Moog (40) and TDK (107) again found zero source-pane pixel changes. The new geometry check reported all 55 Sensors/Moog pages as wider than the equal-pane rule, consistent with their earlier permitted layout; all 107 TDK pages had equal panes. Original PDFs, translations and recovery states retained their fingerprints. Historical acceptance was not rewritten or presented as compliance with the new rule.

## General naming and correction of original-file suffixes

The earlier instruction giving TI originals and translations the same suffixed filename was later corrected by the user. It describes a historical decision, not the current naming policy. All documents now use confirmed identifiers/titles with explicit original/output roles; only generated translations receive the translation suffix. Non-English titles remain in their source language, Chinese titles are not duplicated, papers omit numbering, and confirmed versions follow the Chinese title. TI keeps its number normalization and official-Chinese dual-number rules.

The generic document_filename helper and TI wrapper require an explicit role. Migration validation follows successive immutable state snapshots, preserving the original acceptance and rejecting altered, missing or cyclic history. Desktop renaming and local recovery tests are recorded outside this repository; unchanged PDF bytes do not establish compliance with later layout rules or a new semantic review.

53 synthetic tests now cover explicit original/output roles, generic and TI identifiers, paper-number omission, source languages, version/suffix handling, and multi-hop migration integrity. Local migration verified unchanged bytes for twenty PDFs in ten groups and unchanged historical artifacts. Independent copies of Keysight (12 pages), SDAA401 (9) and Sensors (15) rebuilt with identical text, drawing operations, image/font/Form streams and 144-DPI page pixels; repeated builds were byte-identical. Compared with historical PDFs, rebuilt copies differed by 21, 8 and 27 bytes respectively because of repeated newlines in serialized content streams. A 305-character path passed build, move, read and render checks; Windows process working-directory limits were handled using a shorter working directory and explicit file paths. These checks preserve historical acceptance and do not constitute a new translation review.

## Limits and future changes

There is no automatic translation or universal layout engine. Translation, inventory coverage and page inspection remain model tasks. The tool cannot reliably detect every omitted sentence, flattened table, misplaced caption, clipped glyph, missing ToUnicode mapping or bad reading order. Heuristics are deliberately warnings. With a state inventory, figure hints use explicit caption blocks; without one they match unique extractable figure numbers. Incorrect inventory, repeated references and image-only captions can still evade or mislead the check. Font coverage validates declared draw-time runs and source fonts, not every final PDF glyph program. Review evidence checks consistency, not the observer’s understanding.

Automatic structure checks do not establish accessibility, form behavior, layer semantics, digital-signature validity or full bookmark hierarchy equivalence. Keep these limits in any delivery claim. Extend tests for concrete failures as they arise; avoid adding a broad layout engine or hardcoded vendor rules without a corresponding user need.
