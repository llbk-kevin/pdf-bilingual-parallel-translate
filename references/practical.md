# Practical workflow interface

Use the main entry's practical/strict rules. The examples below are executable interfaces, not commands to run without substituting task paths. Read inplace.md only for glyph splitting, unusual geometry or unsupported interactions. Do not copy its strict full-book review requirements into a practical task.

## Prepare and translate

Use an existing suitable environment or isolated install of requirements.txt; no external translation service is used. Find a permitted Chinese TTF/OTF font (register fallbacks if needed). Quote paths. Run from the document's working folder:

~~~text
python SKILL/scripts/pipeline.py prepare --source ORIGINAL.pdf --state recovery/state.json --pages 1,16,34-36 --font CHINESE.ttf --profile practical
~~~

--pages uses one-based original physical pages; all is default. A selection is an explicit sample: output pages are sequential, source_page remains original numbering. Links/bookmarks outside it are disclosed as omitted, never redirected. Full-document scope still requires all original pages. Fonts are referenced with hashes; keep them available for rebuilding. The resulting PDF embeds its used subset and needs no external font for reading.

prepare freezes scripts next to state, and writes inventory.json and preflight.json. Use this frozen pipeline for all further commands, including verify/review/publish; do not revert a helper variable to SKILL/scripts/pipeline.py. A repository update does not update an existing recovery package. If maintenance changes are needed, create a separately versioned recovery package and keep the original history. Read compact inventory first, not the large glyph state. Source groups/lines help identify paragraphs but do not establish reading order. Inspect source pages (use pdf_tools.py render ORIGINAL.pdf --pages SELECTION --out work/source, or another renderer) before deciding covers and formulas. Preflight flags are cues, not automatic translation decisions. Formula-density hints are heuristic and nonblocking; encoding problems and visible source context take precedence.

Write edits.json, then apply. Example native paragraph and retained label:

~~~json
{"blocks":[
 {"page":1,"id":"paragraph-1","merge_ids":["EXTRACTED-ID-1","EXTRACTED-ID-2"],"method":"replace","translation":"完整段落的中文。","font_size":10,"font_size_min":9},
 {"page":1,"id":"EXTRACTED-FORMULA-ID","method":"preserve","reason":"Original formula and values retained"}
],"inventory_reviewed_pages":[1]}
~~~

Use actual IDs and verify source text. A new merged ID must be unique or belong to its own merge_ids; do not recycle another paragraph's ID. merge_ids concatenates source glyph references and unions source boxes; never merge across columns/cells. Use simple edits without merge_ids for existing paragraphs. After the merge example above has succeeded, later edits address its new ID directly, e.g. {"blocks":[{"page":1,"id":"paragraph-1","font_size":9,"font_size_min":8}]}; do not repeat the removed source merge_ids. Formula/prose mixtures may need glyph splitting using inplace.md; do not reconstruct an entire formula from extracted garbage. The model can write a small JSON-edit operation for that exceptional case; routine translations use apply. All native glyphs must retain exactly one owner. Preserve terse identifiers, units, dimensions and formulas; translate meaningful explanations. Do not mark English prose preserve merely to avoid translating it.

New image/outline cover example (coordinates are visible top-left PDF points):

~~~json
{"blocks":[{"page":34,"id":"scan-note-1","method":"cover","kind":"text","source_text":"Visible English label","source_bbox":[10,20,90,32],"cover_bbox":[10,20,90,32],"allowed_bbox":[10,20,90,32],"translation":"中文说明","font_size":8,"reason":"Local raster label; bounds checked against drawing"}],"inventory_reviewed_pages":[34]}
~~~

For coordinates measured on a source render, add top-level "source_render_index":"work/source/index.json" (relative to the edits JSON). Every supplied source_bbox/cover_bbox/allowed_bbox in that batch is then in ORIGINAL source-image pixels; apply verifies the source fingerprint/image dimensions and converts using recorded DPI. Do not estimate a scale from a resized viewer or mix point/pixel boxes in one batch. Without source_render_index, boxes remain PDF points. Never use bilingual or cropped images as this source index.

Only add covers at verified positions. Extension of allowed_bbox requires expansion_reason describing adjacent empty space, never another table cell. apply also accepts context_pages keyed by source page, link_overrides, glossary and issues. Use link_overrides_patch for incremental corrections, e.g. {"link_overrides_patch":{"1":[{"source_link":0,"target_block":"paragraph-1","target_text":"设计","occurrence":2}]}}. Entries upsert by source_link and keep other links; legacy link_overrides replaces the whole page list (an empty list clears it). Do not use both for the same page. occurrence is one-based among matches inside target_block; specify it when an anchor repeats. In link_overrides, source_link is ZERO-based among the original page's /Link annotations (0 means its first link), not a one-based page number; verify generated page.link_mappings against original clickable regions. For translated link text use target_block plus target_text for the corresponding anchor; changing glossary/layout is a shared dependency. Practical defaults to page-local review dependency, plus explicitly declared context_pages; strict keeps legacy whole-document dependency unless context has been reviewed and declared. Editing authoring state does not overwrite earlier candidates/review history.

~~~text
python recovery/pipeline.py apply --state recovery/state.json --edits edits.json
python recovery/pipeline.py build --state recovery/state.json
~~~

Build returns candidate PDF, generated state and font runs. Always use returned generated state in verify/review/publish. A partial build --pages 16 is useful during adjustment but cannot pass final acceptance for a five-page sample. Group conflicts by page/type from last-error.json, fix together, then rebuild. Link mapping failures are collected across selected pages as link_conflicts with page, source_link and source_bbox; fix the batch instead of rebuilding once per link. Set both font_size and font_size_min when lowering the requested size; the minimum must not exceed it. Null/absent font_size_min means fixed requested size. Never repeatedly lower a size below readability to force success.

## Check once and record real observations

~~~text
python recovery/pipeline.py verify --state work/RETURNED.state.json
~~~

verify performs state/font/audit checks and produces the source, output and relevant difference images in one pass. It returns a render_index, grouped findings and review_needed source pages. Read detailed audit only for actionable findings. Repeating verify on identical inputs reuses hashed evidence instead of rendering. Raw pixel values and mechanical_pass remain unchanged even when a practical difference is retained.

Actually open review_needed page images. Inspect main text/figures and coverage; zoom only suspected blockers. One view is not a quota: revisit if a concrete problem requires it, not to eliminate every tiny imperfection. Write observations.json with real image-view event references or specific observations, then:

~~~json
{"reviewer":"actual-agent-or-person","pages":[{"page":1,"evidence":"Actual image view reference and readability observations","retained":["Minor line break retained"],"retain_right_difference":"If a reported right-side difference was actually inspected: why it does not impair reading"}],"structure_notes":"Basic readability and requested coverage checked"}
~~~

~~~text
python recovery/pipeline.py review --state work/RETURNED.state.json --observations observations.json
~~~

For pages containing covers, verify lists cover_review_needed. Compare these regions with the source, including table numbers, leader lines and pads underneath: the pixel audit masks declared covers and cannot prove they are safe. After that actual comparison set "covers_checked":true on the page observation; this records the covered block IDs without requiring hand-written per-block attestations. A generic full-page glance is insufficient when the cover could hide a drawing. If nearby digits cannot be read at that scale, enlarge that local region once and compare the actual values/row alignment on both sides before covers_checked. A correct DPI conversion does not prove that measured boxes identify the correct label. Never widen a label cover into the numeric column to hide residual English.

Do not fill observations before viewing. Do not directly edit qc to pass. Rendering never creates viewed records. retain_right_difference only dispositions the exact current right_graphics_changed_outside_recorded_regions finding in practical mode. It cannot waive source differences, fonts, missing pages or other errors. Do not supply it for an obscured figure. Strict mode still requires mechanical audit success.

After changing authoring state and rebuilding, run verify with --previous-state OLD_ACCEPTED.state.json. Exact page pixels, rendering settings and page dependencies must match to reuse observations. Original reviewer, timestamp and evidence survive. For those reused pages, exact-matching retained audit decisions and page notes also survive; changed findings are not waived. Only changed/dependent pages need new viewing; the final complete candidate still gets automated checks. If shared fonts/layout/context changes affect other pages they will be invalidated. Do not fabricate reuse by editing fingerprints.

## Deliver and maintain

~~~text
python recovery/pipeline.py publish --state work/RETURNED.state.json --output ACCEPTED.pdf
~~~

publish creates a Markdown delivery note and publication record, with source/output hashes in state, resource deltas, scope, retained issues and recovery instructions. Source-size comparison for a sample uses the complete source PDF and is clearly labeled; it is not a same-page compression ratio. Recovery smoke checks frozen source/font/builder/state consistency. Independent reconstruction and repeated-build resource tests are maintenance regressions, not mandatory per-document rituals.

Operations log their duration/outcome in pipeline-events.jsonl. Record translation/viewing time and tool counts in the task report; machine logs do not measure model reasoning tokens. Do not promise time-saving percentages from differently sized tasks. Full errors are saved to last-error.json, with a compact CLI summary. Existing files require explicit --overwrite. Low-level strict/manual tools remain available when the runner does not cover an actual exceptional case.
