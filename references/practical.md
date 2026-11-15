# Practical workflow interface

Use the main entry's practical/strict rules. The examples below are executable interfaces, not commands to run without substituting task paths. Read inplace.md only for glyph splitting, unusual geometry or unsupported interactions. Use the selected profile and declared page scope.

## Prepare and translate

Before running `prepare`, complete [the naming procedure](naming.md) and use the confirmed source path and working folder. While confirmation is pending, perform read-only source and path checks.

Use an existing suitable environment or isolated install of requirements.txt; no external translation service is used. Find a permitted Chinese TTF/OTF font (register fallbacks if needed). Quote paths. Run from the document's working folder:

~~~text
python SKILL/scripts/pipeline.py prepare --source ORIGINAL.pdf --state recovery/state.json --pages 1,3-5 --font CHINESE.ttf --profile practical
~~~

--pages uses one-based original physical pages; all is default. A selection is an explicit sample: output pages are sequential, source_page remains original numbering. Links/bookmarks outside it are disclosed as omitted, never redirected. Full-document scope still requires all original pages. Fonts are referenced with hashes; keep them available for rebuilding. The resulting PDF embeds its used subset and needs no external font for reading.

prepare freezes scripts next to state, and writes inventory.json and preflight.json. Use this frozen pipeline for all further commands, including verify/review/publish; do not revert a helper variable to SKILL/scripts/pipeline.py. Use a separate recovery directory when testing script changes on the current task. Read compact inventory first, not the large glyph state. Source groups/lines help identify paragraphs but do not establish reading order. Inspect source pages (use pdf_tools.py render ORIGINAL.pdf --pages SELECTION --out work/source, or another renderer) before deciding covers and formulas. Preflight flags are cues, not automatic translation decisions. Formula-density hints are heuristic and nonblocking; encoding problems and visible source context take precedence. Install requirements.txt for AES support. missing_encryption_dependency identifies a missing backend, and password_required identifies a source that needs a password. Preflight checks links against the full declared selection and reports sample_link_omitted for targets outside a sample. In practical mode confirmed empty or undefined named destinations are recorded with their names when available; link appearance and bookmark titles remain. Strict mode requires valid navigation.

Write edits.json, then apply. Example native paragraph and retained label:

~~~json
{"blocks":[
 {"page":1,"id":"paragraph-1","merge_ids":["EXTRACTED-ID-1","EXTRACTED-ID-2"],"method":"replace","translation":"完整段落的中文。","font_size":10,"font_size_min":9},
 {"page":1,"id":"EXTRACTED-FORMULA-ID","method":"preserve","reason":"Original formula and values retained"}
],"inventory_reviewed_pages":[1]}
~~~

Use actual IDs and verify source text. A new merged ID must be unique or belong to its own merge_ids; do not recycle another paragraph's ID. merge_ids concatenates source glyph references and unions source boxes; never merge across columns/cells. Use simple edits without merge_ids for existing paragraphs. After the merge example above has succeeded, later edits address its new ID directly, e.g. {"blocks":[{"page":1,"id":"paragraph-1","font_size":9,"font_size_min":8}]}; do not repeat the removed source merge_ids. Formula/prose mixtures may need glyph splitting using inplace.md; do not reconstruct an entire formula from extracted garbage. The model can write a small JSON-edit operation for that exceptional case; routine translations use apply. All native glyphs must retain exactly one owner. Preserve terse identifiers, units, dimensions and formulas; translate meaningful explanations. Do not mark English prose preserve merely to avoid translating it. Use unresolved_count and unresolved_by_page from apply to check the remaining blocks. Review prefilled preserve blocks and submit edits only for changed decisions. An invalid merge reports the source page, target block and missing IDs.

New image/outline cover example (coordinates are visible top-left PDF points):

~~~json
{"blocks":[{"page":3,"id":"scan-note-1","method":"cover","kind":"text","source_text":"Visible English label","source_bbox":[10,20,90,32],"cover_bbox":[10,20,90,32],"allowed_bbox":[10,20,90,32],"translation":"中文说明","font_size":8,"reason":"Local raster label; bounds checked against drawing"}],"inventory_reviewed_pages":[3]}
~~~

For coordinates measured on a source render, add top-level "source_render_index":"work/source/index.json" (relative to the edits JSON). Every supplied source_bbox/cover_bbox/allowed_bbox in that batch is then in ORIGINAL source-image pixels; apply verifies the source fingerprint/image dimensions and converts using recorded DPI. Do not estimate a scale from a resized viewer or mix point/pixel boxes in one batch. Without source_render_index, boxes remain PDF points. Never use bilingual or cropped images as this source index.

Only add overlays at verified corresponding positions. Practical acceptance is readable Chinese with an understandable association to the source; it does not require complete erasure of the English, exact label boundaries or matched background colors. Keep small remnants instead of enlarging boxes or repeatedly rebuilding. cover_fill and cover_text_color optionally set RGB triples in [0,1]; the defaults are white and black. Choose a readable style once, without automatic color matching. Printed model names, board markings and tiny software UI labels can remain when translated captions/explanations provide the needed meaning. Extension of allowed_bbox requires expansion_reason describing adjacent empty space, never another table cell. apply also accepts context_pages keyed by source page, link_overrides, glossary and issues. Use link_overrides_patch for incremental corrections, e.g. {"link_overrides_patch":{"1":[{"source_link":0,"target_block":"paragraph-1","target_text":"设计","occurrence":2}]}}. Entries upsert by source_link and keep other links; link_overrides replaces the whole page list (an empty list clears it). Do not use both for the same page. occurrence is one-based among matches inside target_block; specify it when an anchor repeats. In link_overrides, source_link is ZERO-based among the original page's /Link annotations (0 means its first link), not a one-based page number; verify generated page.link_mappings against original clickable regions. For translated link text use target_block plus target_text for the corresponding anchor; changing glossary/layout is a shared dependency. Practical defaults to page-local review dependency, plus explicitly declared context_pages; strict uses whole-document dependency unless context has been reviewed and declared. Editing authoring state does not overwrite earlier candidates/review history.

~~~text
python recovery/pipeline.py apply --state recovery/state.json --edits edits.json
python recovery/pipeline.py build --state recovery/state.json
~~~

apply returns preview_argv as an argument array using the current frozen runner, authoring state and changed pages. Pass it directly to a subprocess API (do not join it into an unquoted shell command). During local adjustments use this preview, then omit --pages for final full selection. Later builds should omit --source: the frozen state already identifies it. A mismatched override reports expected/supplied paths and whether the supplied file exists; it does not authorize changing the source fingerprint.

Build returns candidate PDF, generated state and font runs. Always use returned generated state in verify/review/publish. Use --pages 3 for a local preview, then build the complete declared scope for delivery. Group conflicts by page/type from last-error.json, fix together, then rebuild. Link mapping failures are collected across selected pages as link_conflicts with page, source_link and source_bbox; fix the batch instead of rebuilding once per link. Set both font_size and font_size_min when lowering the requested size; the minimum must not exceed it. Null/absent font_size_min means fixed requested size. Never repeatedly lower a size below readability to force success. preserved_glyph_removed identifies missing characters, source positions, preserved blocks and related replacements. Inspect the source crop and related masks first. If the same character and position recur, diagnose the cause before retrying; then repair confirmed collisions and preview the complete formula.

## Resume a long document

Use the frozen runner to find missing work by original physical page:

~~~shell
python recovery/pipeline.py status --state recovery/state.json --pages 1-40
python recovery/pipeline.py apply --state recovery/state.json --edits work/chapter-1.json --edits work/chapter-2.json
~~~

For multiple documents, long documents or independent review, use [coordination.md](coordination.md) for packages, ownership and recovery. Use the authoring state for translation progress and the returned candidate state for verification and review progress. A failing batch leaves the authoring state unchanged. A preview can omit links to unselected pages and cannot be published. Use a complete build of the declared scope for delivery.

## Check once and record real observations

~~~text
python recovery/pipeline.py verify --state work/RETURNED.state.json
~~~

verify performs state/font/audit checks and produces the source, output and relevant difference images in one pass. It returns a render_index, grouped findings and review_needed source pages. Read detailed audit only for actionable findings. The first verify reports `inventory_review_needed`. Include `"inventory_reviewed": true` in a page observation only after confirming its source inventory against the visible page. Recording this on the same candidate reuses the audit and renders. Verify reports `rendered_pages`, `source_rendered_pages`, `mechanical_reused_pages` and `state_written_bytes`. Inspect the event log for elapsed times. After an edit, unchanged original and candidate images may be reused; document-level checks still run. Raw pixel values and mechanical_pass remain unchanged even when a practical difference is retained.

Open the bilingual pages listed in review_needed. Use difference images and local zoom to investigate specific concerns. When an independent reviewer is assigned, have that reviewer record their observations. If a page needs repair, submit observations for the pages already viewed and clear, and report the repair separately. Copy output_sha256 and render_index_sha256 from this verify result.

~~~json
{"output_sha256":"COPY_FROM_VERIFY","render_index_sha256":"COPY_FROM_VERIFY","reviewer":"actual-agent-or-person","pages":[{"page":1,"evidence":"Actual image view reference and readability observations","retained":["Minor line break retained"],"retain_right_difference":"If a reported right-side difference was actually inspected: why it does not impair reading"}],"structure_notes":"Basic readability and requested coverage checked"}
~~~

~~~text
python recovery/pipeline.py review --state work/RETURNED.state.json --observations observations.json
~~~

verify lists cover_review_needed. Compare each overlay with the source and check label association, table values, leader lines and key graphics. Enlarge local details as needed. After comparison set "covers_checked":true in the page observation to record the covered block IDs.

Do not fill observations before viewing. Do not directly edit qc to pass. Rendering never creates viewed records. retain_right_difference only dispositions the exact current right_graphics_changed_outside_recorded_regions finding in practical mode. It cannot waive source differences, fonts, missing pages or other errors. Do not supply it for an obscured figure. Strict mode still requires mechanical audit success.

Batch repairs, preview the affected pages, then build the complete candidate. Run verify --previous-state PREVIOUS.state.json even if only some pages were recorded. Repeat the option for multiple relevant candidates or packages. It checks pixels, settings and dependencies per page and keeps each valid record’s original viewer, time and evidence. Valid observations on the current candidate take priority. Follow review_needed and record a new decision for any changed difference finding. Automated checks still cover the complete candidate.

review returns observations_saved, saved_pages, reviewed_pages and review_needed. Check ready and errors for delivery readiness. Use verify --previous-state to reuse partial observations.

## Deliver and maintain

~~~text
python recovery/pipeline.py publish --state work/RETURNED.state.json --output ACCEPTED.pdf
~~~

publish writes 交付说明.md inside the task folder and publication.json beside the accepted state, returning their paths and the task_dir. Only the accepted PDF is copied to --output. The note includes source/output hashes, resource deltas, scope, retained issues and recovery instructions. The task folder is inferred from the state parent work/, recovery/ or recovery-vN/; for other layouts specify publish --task-dir DIR containing the state. Notes, record and output conflicts are checked before copying, and replacing existing targets requires --overwrite. Source-size comparison for a sample uses the complete source PDF and is clearly labeled; it is not a same-page compression ratio. Recovery checks verify the frozen dependencies. Run the returned recovery_argv only when rebuilding is needed. It writes work/rebuild/accepted.rebuilt.pdf and sidecars inside the task folder.

pipeline-events.jsonl records command timings and outcomes. Capture exit status, stdout and stderr on failure, then read last-error.json beside --state. Existing targets require explicit --overwrite.

## Diagnostic and review handoff

Use prepare's command_prefix followed by the frozen pipeline.py and its arguments. It runs with the recorded import paths and checks dependency versions in a fresh process. Source-symbol font hints identify common symbols needing a registered fallback font or source preservation. publish probes the actual recovery prefix before copying the accepted PDF.

apply reports changed_pages, preview_skipped_pages and unresolved_by_page. preview_argv contains only resolved changed pages. After merging, submit subsequent edits against the current merged ID.

Local build checks right-side link anchors for all destinations in the final delivery scope, including pages absent from the preview. Packages retain final_source_pages. Truly excluded sample targets remain recorded as omitted. Link, font, fit and collision findings are collected before PDF serialization. Inspect the listed source_link, block, character and required/available dimensions together before rebuilding. Each failed command retains its full diagnostic under diagnostics/ and links it from last-error.json and pipeline-events.jsonl.

verify returns review_handoff and observations_template paths. Copy the template to a new observation file and fill the actual reviewer and viewed pages. Its pages starts empty. Missing binding fields and mismatched fingerprints produce distinct errors. Reuse actual partial observations with --previous-state after repairs. When independent review is assigned, the translator hands over the full machine-checked candidate after local readability checks.
