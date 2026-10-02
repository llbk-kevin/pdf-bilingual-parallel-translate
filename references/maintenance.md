# Skill maintenance and verified scope

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

The integration tests generate small PDFs in temporary directories using ReportLab and pypdf; they do not require the desktop documents or licensed font files. Runtime tools require pypdf, pypdfium2 and Pillow. Development additionally uses ReportLab. First-release verified versions: pypdf 6.10.0, pypdfium2 5.13.0, Pillow 12.3.0, ReportLab 4.4.9, on Windows. The requirements files allow compatible minor updates; rerun relevant tests after dependency updates. Inventory intentionally uses pypdf 6.x encoded-stream internals, so a major upgrade requires review.

Run the installed skill-creator validator if available, and inspect UTF-8/BOM status, Markdown links and UI metadata. Before commit, review git diff and tracked files. Exclude task inputs, outputs, state, render caches, font binaries and secrets. Use Conventional Commits with an English type/scope, Chinese description and a multiline Chinese body for substantive changes. Keep Chinese comments for .gitignore groups.

Commit and push validated changes to origin/main as the selected maintenance policy. Never force-push or discard unrelated work. If remote state has advanced, fetch and integrate only understood changes, then validate the result. If authentication or push fails, preserve local commits and report the exact remaining step. Ordinary PDF translation does not modify or synchronize this repository.

## First-release validation

18 synthetic integration tests cover nested/shared image resources; original duplication versus newly introduced copies; duplicate font streams; changed Decode semantics; lossless palette recompression and numeric representation; rotation/crop; source raster corruption; removed links/bookmarks; table shape and missing translations; missing figure anchors; caption displacement and pipe-table hints; source/output/builder/layout-input fingerprint changes; stale/incomplete reviews; render indices; overwrite protection; and deterministic read-only audits.

Three original/previous-translation pairs totaling 74 pages were locally audited: NSI826x (32), NSI8608 (20), and a flyback presentation (22). All original panes passed the raster comparison, image byte increments were zero, and existing duplicate resources were not mislabeled as newly introduced. Warnings identified candidate table flattening, caption displacement, small Chinese and changed links. These are diagnostic findings, not semantic certification of the old translations.

A separately generated seven-page local sample covered the NSI826x double-column first page, parameter table, multi-figure page and repeated-formula page; an NSI8608 circuit explanation page; and flyback diagram/landscape-table pages. All seven pages were individually inspected, with dense tables enlarged. The sample reused original images, introduced no bitmap bytes, retained real table cells and repeated equations, and used shared subset fonts. Rebuilding produced the same PDF hash. Source sample: 1,742,417 bytes; bilingual sample: 2,125,713 bytes; image/Form delta: zero; added font streams: 162,063 encoded bytes. Sample PDFs, task builder, translations and recovery data are local deliverables, not repository fixtures.

## Limits and future changes

There is no automatic translation or universal layout engine. Translation, inventory coverage and page inspection remain model tasks. The tool cannot reliably detect every omitted sentence, flattened table, misplaced caption, clipped glyph, missing ToUnicode mapping or bad reading order. Heuristics are deliberately warnings. Figure hints match unique extractable figure numbers and large vertical displacement; repeated references and image-only captions may evade them.

Automatic structure checks do not establish accessibility, form behavior, layer semantics, digital-signature validity or full bookmark hierarchy equivalence. Keep these limits in any delivery claim. Extend tests for concrete failures as they arise; avoid adding a broad layout engine or hardcoded vendor rules without a corresponding user need.
