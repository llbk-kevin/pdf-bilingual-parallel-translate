# Skill maintenance and verified scope

This reference is for skill maintenance. Document names and subjects in historical validation records describe past checks only; do not use them to infer a new translation task's domain or preferred style.

## Repository and installation

The maintained repository is llbk-kevin/pdf-bilingual-parallel-translate, with main as its default branch. The global entry is <CODEX_HOME>/skills/pdf-bilingual-parallel-translate. A newly created ordinary directory stays there until CC Switch manages it. Do not manually migrate it.

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

Three original/previous-translation pairs totaling 74 pages were locally audited: NSI826x (32), NSI8608 (20), and a flyback presentation (22). All original panes passed the raster comparison, image byte increments were zero, and existing duplicate resources were not mislabeled as newly introduced. Warnings identified candidate table flattening, caption displacement, small Chinese and changed links.

A separately generated seven-page local sample covered the NSI826x double-column first page, parameter table, multi-figure page and repeated-formula page; an NSI8608 circuit explanation page; and flyback diagram/landscape-table pages. All seven pages were individually inspected, with dense tables enlarged. The sample reused original images, introduced no bitmap bytes, retained real table cells and repeated equations, and used shared subset fonts. Rebuilding produced the same PDF hash. Source sample: 1,742,417 bytes; bilingual sample: 2,125,713 bytes; image/Form delta: zero; added font streams: 162,063 encoded bytes. Sample PDFs, task builder, translations and recovery data are local deliverables, not repository fixtures.

## Naming, recovery and evidence upgrade

The initial migration of requirements reduced “do not automatically rename the original” to preserving its filename, losing identification, proposal, confirmation and execution rules. This was an incomplete requirements migration. The naming reference restores the whole workflow and the user-selected convention that TI English originals and translated outputs share a basename in separate directories.

35 synthetic tests now cover the original checks plus TI formatting/omitted IDs, title normalization, duplicate suffix prevention, same-name source/output separation, assigned-font missing glyphs and fallback, state-driven full table cells, overflow, external input retention, deterministic rebuilds, actual render evidence, strict reuse/context invalidation, path-only relocation, fixed-scale fractional geometry, empty/explicit passwords, caption roles and uncompressed streams. Test fonts are generated procedurally.

Local regression audited Sensors (15), Moog (40) and TDK (107), totaling 162 pages: all original panes had zero changed pixels with the uniform-matrix renderer. Moog’s former dimension-dependent sampling mismatch disappeared without loosening tolerances. TDK’s empty user password worked through the standard reader; 103 small marginal-text findings were distinguished from three footnote-related small-text warnings. Those warnings still need documented human interpretation. The historical benchmark font was independently confirmed to lack U+2243 and U+2095; declared assigned-font checking now catches such absence even when extraction succeeds. This does not replace final visual inspection.

The task-local migration records and independent rebuild evidence stay outside the skill repository. Existing version 1 packages retain their original review history; a rename is not an invented version 2 acceptance. Do not claim all previous translations were re-reviewed during this maintenance.

## Equal panes and confirmed page numbering

42 synthetic tests cover the previous behavior plus equal-pane construction on mixed/fractional pages, rejection of wider/narrower legacy widths, output geometry and source placement errors with unchanged 0.1 pt tolerance, explicit original/physical page labels, unnumbered covers, actual page-label font runs and invalidation. Rotation/crop fixtures also assert equal visible panes. The optional numbering fields do not identify printed labels automatically.

Generate visual fixtures outside the repository with tests/generate_layout_samples.py --out <task-dir>/samples --font <permitted-Chinese-TrueType-font>, adding --face-index if needed. The font and outputs stay local. Three documents totaling seven pages cover an unnumbered cover plus iv/A-3 labels, wholly unnumbered pages including a blank page, and a locally reduced table with nearby margin use. All seven pages and the enlarged table were actually inspected; source panes were pixel-identical, image/Form byte deltas were zero, font checks and state checks passed, and repeated builds were byte-identical. Keeping the table at the 11.5 pt body size overflowed; 8.5 pt fit while body text stayed 11.5 pt.

Read-only regression on Sensors (15), Moog (40) and TDK (107) again found zero source-pane pixel changes. The new geometry check reported all 55 Sensors/Moog pages as wider than the equal-pane rule, consistent with their earlier permitted layout; all 107 TDK pages had equal panes. Original PDFs, translations and recovery states retained their fingerprints. Historical acceptance was not rewritten or presented as compliance with the new rule.

## General naming and correction of original-file suffixes

The earlier instruction giving TI originals and translations the same suffixed filename was later corrected by the user. It describes a historical decision, not the current naming policy. All documents now use confirmed identifiers/titles with explicit original/output roles; only generated translations receive the translation suffix. Non-English titles remain in their source language, Chinese titles are not duplicated, papers omit numbering, and confirmed versions follow the Chinese title. TI keeps its number normalization and official-Chinese dual-number rules.

The generic document_filename helper and TI wrapper require an explicit role. Migration validation follows successive immutable state snapshots, preserving the original acceptance and rejecting altered, missing or cyclic history. Desktop renaming and local recovery tests are recorded outside this repository; unchanged PDF bytes do not establish compliance with later layout rules or a new semantic review.

53 synthetic tests now cover explicit original/output roles, generic and TI identifiers, paper-number omission, source languages, version/suffix handling, and multi-hop migration integrity. Local migration verified unchanged bytes for twenty PDFs in ten groups and unchanged historical artifacts. Independent copies of Keysight (12 pages), SDAA401 (9) and Sensors (15) rebuilt with identical text, drawing operations, image/font/Form streams and 144-DPI page pixels; repeated builds were byte-identical. Compared with historical PDFs, rebuilt copies differed by 21, 8 and 27 bytes respectively because of repeated newlines in serialized content streams. A 305-character path passed build, move, read and render checks; Windows process working-directory limits were handled using a shorter working directory and explicit file paths. These checks preserve historical acceptance and do not constitute a new translation review.

## Sibling PDF delivery and disposable working folder

The default now keeps the original and accepted translation beside a same-stem working folder. Per-document notes, recovery, drafts and review evidence remain inside that folder; only a hash-verified accepted PDF is published outside it. The builder CLI and state schema are unchanged.

54 synthetic tests pass. The added delivery-layout fixture verifies relative source/font/output references, byte-identical publication, unchanged review evidence and final-state consistency. In a disposable copy it removes the resolved working-folder path, then verifies unchanged PDF hashes, extracted text (including Chinese) and rendered page pixels. This maintenance does not migrate existing user PDFs or rewrite their historical acceptance.

## Checking responsibilities and future changes

The model translates, confirms source inventory coverage and views pages; scripts check state, fonts, resources and rendering. Heuristic findings guide inspection alongside the source page. With a state inventory, figure hints use explicit caption blocks; without one they match unique extractable figure numbers. Repeated references and image-only captions need confirmation against the source image. Font checks use actual draw-time runs and source fonts; review records check consistency among files, pages and evidence.

Add tests for concrete failures and extend features according to actual tasks.

## Default in-place translation (state v3)

The default now reuses the complete source page on both panes, removes selected right-side native glyphs, and draws local Chinese replacements. The old example remains an explicit v1/v2 compatibility builder; no silent fallback is allowed. New recoverable state records immutable source glyph facts, ownership/ranges, method, allowed/actual bounds, real font assignments and source geometry/fingerprints. See [inplace.md](inplace.md).

Twenty additional procedural regressions cover same-source shared images and soft masks through nested Forms; left-pane pixel isolation; colored fills and retained formulas; crop/rotation/UserUnit/mixed sizes; hidden OCR and outlined-label covers; overflow and source changes; glyph splitting and zero-width ligature tails; actual outline-based collisions; word/model wrapping, bounded font fitting and sub/sup baselines; font sharing/subsetting and repeatability; nullable raw link modes, rotated destinations and clickable anchors following reflow; static appearance migration with annotations visibly enabled and independent left/right objects; unsupported annotations/text clipping; tight right-pane region checks that detect graphics damage even inside allowed layout boxes; external input retention; and generated numbering. They contain no user PDF/font binaries. Real sample trials and their review evidence stay in the document task folder.

Verified implementation details: global deflate can re-encode source images, so only non-image streams are compressed; PDFium ignores UserUnit, so its rendering copy is normalized in memory; MuPDF glyph_bbox can return a font-wide box, so translated ink bounds use fontTools outlines and source collision masks use drawing traces. Raw get_links coordinates cannot represent nullable XYZ axes reliably; migration reads original PDF destination arrays. Font serialization disables timestamp recalculation.

## Practical runner and sample scope

The pipeline entry defaults new tasks to practical and freezes its scripts beside authoring state. Missing profile fields retain strict semantics. It batches JSON edits/paragraph merges, caches fingerprint-matched builds, combines audit and image rendering, records actual observations separately, and publishes byte-identical accepted candidates with generated notes. Explicit sample scope preserves original source-page mappings and records omitted out-of-scope links.

The additional pipeline regressions cover sample completeness versus legacy full coverage, atomic edits and merged glyph ownership, null font minimum, audit/render cache reuse, unviewed-state rejection, exact right-difference dispositions without source-damage waivers, unchanged-page review history reuse, shared-font invalidation, byte-identical publication, partial/repeated resource builds and no-action outline headings with nested destinations. Tests use synthetic observation records. Real independent trials, timings, token statistics and remaining issues belong in the task report outside this repository.

Independent seven-page practical use exposed two specific failures: guessed pixel-to-point scale displaced scan covers onto drawings, and returning to the live runner invalidated the calculated review directory. Pixel-based apply now verifies source-render fingerprints and recorded DPI; cover observations explicitly compare underlying drawing/table content. Review resolves already-bound evidence, and verification cache keys exclude unrelated runner edits. Ninety procedural tests pass, including these repairs. The independent follow-up accepted remaining minor marks without further layout iteration. Historical trial records remain unchanged; live-to-frozen builder path relocation still conservatively invalidates page semantic hashes even when pixels match, and this one-time migration must not be reported as automatic review reuse.

## Parallel practical trial follow-up

A second independent trial exposed sequential link-mapping failures and accidental replacement of a whole page's link corrections. Link conflicts now return a batch with page/link coordinates; link_overrides_patch updates individual source_link entries while legacy full-list replacement remains explicit. Reused page observations now retain only exact-matching accepted findings and page notes, so a harmless unchanged difference does not block local repair delivery. Ninety-three procedural tests pass; a real affected-page rebuild was pixel-identical after the link migration change. Two unsafe image-label covers required local correction and independent reinspection; correct DPI and a covers_checked flag do not establish safe placement. Read the adjacent values at a legible scale, without turning cosmetic marks into another full-document review.


Repeated-letter ligatures can produce a zero-width trace tail with the same character and origin as the visible carrier. Effective bounds ignore empty trace entries so they cannot overwrite the carrier; immutable source glyph facts and ownership checks remain unchanged. A procedural ff fixture reproduces the prior failure and verifies replacement plus left-pane isolation.
