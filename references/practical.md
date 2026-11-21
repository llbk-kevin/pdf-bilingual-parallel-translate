# Practical workflow interface

Use the main entry's practical/strict rules. The examples below are executable interfaces, not commands to run without substituting task paths. Read inplace.md only for glyph splitting, unusual geometry or unsupported interactions. Use the selected profile and declared page scope.

## Prepare and translate

Before `prepare`, confirm [names](naming.md) together with the [agent work plan](coordination.md), then use confirmed paths. While confirmation is pending, perform read-only source and path checks.

Use an existing suitable environment or isolated install of requirements.txt; no external translation service is used. Find a permitted Chinese TTF/OTF font (register fallbacks if needed). Quote paths. Run from the document's working folder:

~~~text
python SKILL/scripts/pipeline.py prepare --source ORIGINAL.pdf --state recovery/state.json --pages 1,3-5 --font CHINESE.ttf --profile practical
~~~

--pages uses one-based original physical pages; all is default. A selection is an explicit sample: output pages are sequential, source_page remains original numbering. Links/bookmarks outside it are disclosed as omitted, never redirected. Full-document scope still requires all original pages. Fonts are referenced with hashes; keep them available for rebuilding. The resulting PDF embeds its used subset and needs no external font for reading.

prepare freezes the current scripts, runtime launcher/configuration and resource-budget module next to state, and writes inventory.json and preflight.json. Use the returned command_prefix plus runner for every subsequent command. The examples below abbreviate this prefix as COMMAND_PREFIX. --workers accepts auto (default) or a positive integer, with machine-wide CPU/memory admission and resource telemetry. Use this frozen pipeline for all further commands, including verify/review/publish; do not revert a helper variable to SKILL/scripts/pipeline.py. Use a separate recovery directory when testing script changes on the current task. Read compact inventory first, not the large glyph state. Source groups/lines help identify paragraphs but do not establish reading order. Use the command arrays below for isolated rendering. Inspect source pages (use pdf_tools.py render ORIGINAL.pdf --pages SELECTION --out work/source, or another renderer) before deciding covers and formulas. Preflight flags are cues, not automatic translation decisions. Formula-density hints are heuristic and nonblocking; encoding problems and visible source context take precedence. Install requirements.txt for AES support. missing_encryption_dependency identifies a missing backend, and password_required identifies a source that needs a password. Preflight checks links against the full declared selection and reports sample_link_omitted for targets outside a sample. In practical mode confirmed empty or undefined named destinations are recorded with their names when available; link appearance and bookmark titles remain. Strict mode requires valid navigation.

Preparation stages extraction, fonts and the cold runtime check before publishing managed files, with the state committed last. Failure preserves an existing recovery package and user-owned files; diagnostics remain available. Same-drive references are relative; cross-drive references are absolute and fingerprinted. No manual font copy is required.

Use the returned commands.source_render_argv once before dispatch. commands.status_argv, inspect_argv and build_argv also include the frozen runtime and exact paths; pass arrays directly to a subprocess API. package returns matching commands for its own state. A shell/import failure is an environment diagnosis, not a reason to bypass the frozen runner.

When changing builder code, invoke the revised repository entry:

~~~text
python SKILL/scripts/pipeline.py refreeze --state recovery/state.json --out recovery-v2
~~~

This accepts only authoring state and a new destination. Source, fonts, edits, glyph ownership, inventory and context remain; QC and package-application receipts are reset for the new version. Source hashes and current state validity are checked. Old scripts, candidates and evidence remain unchanged. The result reports dependency fingerprints and new commands. Re-export affected packages and validate their saved edits with fresh manifests; do not edit dependency/baseline hashes to suppress a conflict.

### Bounded state reads and long commands

Use frozen pipeline inspect instead of parsing the full state in a persistent Node REPL:

~~~text
COMMAND_PREFIX recovery/pipeline.py inspect --state recovery/state.json
COMMAND_PREFIX recovery/pipeline.py inspect --state recovery/state.json --pages 12 --detail blocks --limit 20
COMMAND_PREFIX recovery/pipeline.py inspect --state recovery/state.json --pages 12 --block ACTUAL_ID --detail glyphs --offset 0 --limit 50
~~~

Summary is the default. Blocks require an explicit page selection; glyphs also require a block. Replies contain at most 200 items (default 20), next_offset for paging, and an explicit truncation flag for text beyond 4,000 characters. Reduce --limit if the 256 KiB reply budget is exceeded. Queries never alter the state, QC, diagnostics or event logs. They still load the state in a short-lived Python process, which exits after answering.

For build/verify or other long frozen commands, write the exact argv array to work/job-argv.json. Use the recorded Python executable to run the frozen task_runtime.py (a process wrapper, not a replacement PDF builder):

~~~text
PYTHON recovery/task_runtime.py start --task-dir TASK --job-dir TASK/work/jobs/build-001 --argv-file TASK/work/job-argv.json
PYTHON recovery/task_runtime.py status --job-dir TASK/work/jobs/build-001
PYTHON recovery/task_runtime.py cancel --job-dir TASK/work/jobs/build-001
~~~

Job and argument files must be under TASK/work; job directories are new and never overwritten. --cwd optionally selects a short launch directory, otherwise the task's parent is used. The independent supervisor writes stdout.log, stderr.log and job.json and survives a REPL reset. Status returns paths and bounded error tails, not the full logs/results. Read only the needed tail or diagnostic; do not collect full output with execFile/maxBuffer. Cancellation checks PID plus start time and only terminates that job's worker tree; an orphaned supervisor is reported and can be recovered by cancel. Do not reset a kernel with an unsupervised background child.

Status can be finalizing until the supervisor and its launcher exit; wait for a terminal state before renaming/removing logs. Prefer a working direct CLI tool; if one shell fails, check an available alternative before making Node the default runner.

Before PDF work in a new Node kernel, register it using the coordination session command and keep its record path; this applies to reviewers too. Keep only paths, small edit batches and summaries in Node. Read images one at a time and avoid persistent arrays of image buffers/Base64. Put unavoidable temporary reads in a function scope, then reset at the documented handoff boundary; nulling one variable or forcing GC is not proof that historical module bindings or native buffers were released. Session registration and cleanup commands are in [coordination.md](coordination.md).

Write edits.json, then apply. Example native paragraph and retained label:

~~~json
{"blocks":[
 {"page":1,"id":"paragraph-1","merge_ids":["EXTRACTED-ID-1","EXTRACTED-ID-2"],"method":"replace","translation":"完整段落的中文。","font_size":10,"font_size_min":9},
 {"page":1,"id":"EXTRACTED-FORMULA-ID","method":"preserve","reason":"Original formula and values retained"}
],"inventory_reviewed_pages":[1]}
~~~

Use actual IDs and verify source text. A new merged ID must be unique or belong to its own merge_ids; do not recycle another paragraph's ID. merge_ids concatenates source glyph references and unions source boxes; never merge across columns/cells. Use simple edits without merge_ids for existing paragraphs. After the merge example above has succeeded, later edits address its new ID directly, e.g. {"blocks":[{"page":1,"id":"paragraph-1","font_size":9,"font_size_min":8}]}; do not repeat the removed source merge_ids. Formula/prose mixtures may need glyph splitting using inplace.md; do not reconstruct an entire formula from extracted garbage. The model can write a small JSON-edit operation for that exceptional case; routine translations use apply. All native glyphs must retain exactly one owner. Preserve terse identifiers, units, dimensions and formulas; translate meaningful explanations. Do not mark English prose preserve merely to avoid translating it. Use unresolved_count and unresolved_by_page from apply to check the remaining blocks. Review prefilled preserve blocks and submit edits only for changed decisions. Extraction can include text already occluded by later source drawing. After checking the source image, assign such overlapping underlying glyphs to the same regional replacement instead of preserving them independently; retain immutable glyph facts and migrate links separately. An invalid merge reports the source page, target block and missing IDs.

New image/outline cover example (coordinates are visible top-left PDF points):

~~~json
{"blocks":[{"page":3,"id":"scan-note-1","method":"cover","kind":"text","source_text":"Visible English label","source_bbox":[10,20,90,32],"cover_bbox":[10,20,90,32],"allowed_bbox":[10,20,90,32],"translation":"中文说明","font_size":8,"reason":"Local raster label; bounds checked against drawing"}],"inventory_reviewed_pages":[3]}
~~~

For coordinates measured on a source render, the index is relative to the edits JSON: for TASK/work/edits.json referencing TASK/work/source/index.json, use top-level "source_render_index":"source/index.json" (do not add another work/). Every supplied source_bbox/cover_bbox/allowed_bbox in that batch is then in ORIGINAL source-image pixels; apply verifies fingerprint/image dimensions and converts using recorded DPI. Do not estimate scale from a resized viewer or mix point/pixel boxes. Without source_render_index, boxes remain PDF points. Never use bilingual or cropped images as this source index.

Only add overlays at verified corresponding positions. Practical acceptance is readable Chinese with an understandable association to the source; it does not require complete erasure of the English, exact label boundaries or matched background colors. Keep small remnants instead of enlarging boxes or repeatedly rebuilding. cover_fill and cover_text_color optionally set RGB triples in [0,1]; the defaults are white and black. Choose a readable style once, without automatic color matching. Printed model names, board markings and tiny software UI labels can remain when translated captions/explanations provide the needed meaning. Extension of allowed_bbox requires expansion_reason describing adjacent empty space, never another table cell. apply also accepts context_pages keyed by source page, link_overrides, glossary and issues. Use link_overrides_patch for incremental corrections, e.g. {"link_overrides_patch":{"1":[{"source_link":0,"target_block":"paragraph-1","target_text":"设计","occurrence":2}]}}. Entries upsert by source_link and keep other links; link_overrides replaces the whole page list (an empty list clears it). Do not use both for the same page. occurrence is one-based among matches inside target_block; specify it when an anchor repeats. In link_overrides, source_link is ZERO-based among the original page's /Link annotations (0 means its first link), not a one-based page number; verify generated page.link_mappings against original clickable regions. For translated link text use target_block plus target_text for the corresponding anchor; changing glossary/layout is a shared dependency. Practical defaults to page-local review dependency, plus explicitly declared context_pages; strict uses whole-document dependency unless context has been reviewed and declared. Editing authoring state does not overwrite earlier candidates/review history.

~~~text
COMMAND_PREFIX recovery/pipeline.py apply --state recovery/state.json --edits edits.json
COMMAND_PREFIX recovery/pipeline.py build --state recovery/state.json
~~~

apply reports preview_skipped_pages and unresolved_by_page. Its preview_argv contains only fully resolved changed pages. apply returns preview_argv as an argument array using the current frozen runner, authoring state and changed pages. Pass it directly to a subprocess API (do not join it into an unquoted shell command). During local adjustments use this preview, then omit --pages for final full selection. Later builds should omit --source: the frozen state already identifies it. A mismatched override reports expected/supplied paths and whether the supplied file exists; it does not authorize changing the source fingerprint.

Build returns candidate PDF, generated state and font runs. Always use returned generated state in verify/review/publish. Use --pages 3 for a local preview, then build the complete declared scope for delivery. Local checks resolve translated link anchors for all destinations in the final delivery scope before PDF serialization, including targets outside the preview. Packages retain final_source_pages. Group conflicts by page/type from last-error.json, fix together, then rebuild. Link mapping failures are collected across selected pages as link_conflicts with page, source_link and source_bbox; fix the batch instead of rebuilding once per link. Set both font_size and font_size_min when lowering the requested size; the minimum must not exceed it. Null/absent font_size_min means fixed requested size. After saving, apply reports layout_check counts (passed/adapted/needs_attention/fixed_size), grouped affected pages and an apply-layout.json details path. Overflow does not discard the saved translation. Set readable bounds on representative text classes, then reuse them; no global minimum is imposed. build uses the same trial before redaction. Never repeatedly lower a size below readability to force success. preserved_glyph_removed identifies missing characters, source positions, preserved blocks and related replacements. Inspect the source crop and related masks first. With no related mask, investigate page-wide normalization rather than guessing nearby edits. preserved_duplicate_reduced identifies identical overprinted glyphs reduced to one surviving copy: practical requires viewing the location and retain_right_difference; strict blocks. Raw pixel differences remain measured. If the same character and position recur, diagnose the cause before retrying; then repair confirmed collisions and preview the complete formula.

## Resume a long document

Use the frozen runner to find missing work by original physical page:

~~~shell
COMMAND_PREFIX recovery/pipeline.py status --state recovery/state.json --pages 1-40
COMMAND_PREFIX recovery/pipeline.py apply --state recovery/state.json --edits work/chapter-1.json --edits work/chapter-2.json
~~~

For multiple documents, long documents or independent review, use [coordination.md](coordination.md) for packages, ownership and recovery. Use the authoring state for translation progress and the returned candidate state for verification and review progress. A failing batch leaves the authoring state unchanged. A preview can omit links to unselected pages and cannot be published. Use a complete build of the declared scope for delivery.

## Representative previews and coherent prose

Choose representative pages from the actual source: inline/standalone formulas, dense cells or screenshots as applicable. Translate a small coherent sample, build with preview_argv and view it before repeating the method across the document. This is layout validation, not another full-document review.

Preserve standalone formulas in place. For inline variables, compose a complete Chinese sentence and, when needed, repeat verified short variables/values in that sentence while leaving native glyphs intact. Keep native ownership and record any visible leftovers. Do not split Chinese around each preserved character or spread it across distant blank spaces merely to pass collision checks. Check preserved symbols against any complete formula repeated in translation for duplicate prefixes. Group tables by actual cells, not a fixed x-coordinate split. Preview the whole paragraph, associated formula and table cells; substantive symbols/values cannot be obscured. A few isolated residual glyphs are practical retained details when the complete sentence and formula remain readable.

After unresolved_count reaches zero, still compare the visible page with inventory, especially screenshots, raster graphs and outlined labels absent from extraction. Translate their main explanation/labels with local overlays or a clearly associated Chinese explanation. Do not replace this check with more edits to already translated native text.

## Check once and record real observations

~~~text
COMMAND_PREFIX recovery/pipeline.py verify --state work/RETURNED.state.json
~~~

verify performs state/font/audit checks and produces the source, output and relevant difference images in one pass. It returns a render_index, grouped findings and review_needed source pages. Read detailed audit only for actionable findings. The first verify reports `inventory_review_needed`. Include `"inventory_reviewed": true` in a page observation only after confirming its source inventory against the visible page. Recording this on the same candidate reuses the audit and renders. Verify reports `rendered_pages`, `source_rendered_pages`, `mechanical_reused_pages` and `state_written_bytes`. Inspect the event log for elapsed times. After an edit, unchanged original and candidate images may be reused; document-level checks still run. Raw pixel values and mechanical_pass remain unchanged even when a practical difference is retained.

The translator checks completeness plus representative/conflict pages; the independent reviewer covers the delivered selection. A translator need not register a second formal page-by-page review. Open pages listed in review_needed or inventory_review_needed. During the same actual view, check the source inventory, required covers and any exact difference findings, and record applicable inventory_reviewed/covers_checked/retain_right_difference evidence. Use differences and zoom only for concerns. Independent reviewers submit their own observations; multiple reviewers save separate files for serial registration by the state writer. Save clear-page evidence before repairs, and reuse it through --previous-state. Use review_handoff and copy observations_template to a new file; it binds candidate/render hashes and starts with empty pages. Missing fields and mismatched hashes are diagnosed separately. Never mark a check completed merely to avoid another view.

~~~json
{"output_sha256":"COPY_FROM_VERIFY","render_index_sha256":"COPY_FROM_VERIFY","reviewer":"actual-agent-or-person","pages":[{"page":1,"evidence":"Actual image view reference and readability observations","retained":["Minor line break retained"],"retain_right_difference":"If a reported right-side difference was actually inspected: why it does not impair reading"}],"structure_notes":"Basic readability and requested coverage checked"}
~~~

~~~text
COMMAND_PREFIX recovery/pipeline.py review --state work/RETURNED.state.json --observations observations.json
~~~

verify lists cover_review_needed. Compare each overlay with the source and check label association, table values, leader lines and key graphics. Enlarge local details as needed. After comparison set "covers_checked":true in the page observation to record the covered block IDs.

Do not fill observations before viewing. Do not directly edit qc to pass. Rendering never creates viewed records. retain_right_difference only dispositions the exact current right_graphics_changed_outside_recorded_regions finding in practical mode. It cannot waive source differences, fonts, missing pages or other errors. Do not supply it for an obscured figure. Strict mode still requires mechanical audit success.

Batch repairs, preview the affected pages, then build the complete candidate. Run verify --previous-state PREVIOUS.state.json even if only some pages were recorded. Repeat the option for multiple relevant candidates or packages. It checks pixels, settings and dependencies per page and keeps each valid record’s original viewer, time and evidence. Valid observations on the current candidate take priority. Follow review_needed and record a new decision for any changed difference finding. Automated checks still cover the complete candidate.

review returns observations_saved, saved_pages, reviewed_pages and review_needed. Check ready and errors for delivery readiness. Use verify --previous-state to reuse partial observations.

Report observation reuse separately from mechanical cache reuse and actual rendered pages. A text edit can change a shared embedded font subset even with unchanged registered fonts, invalidating painting fingerprints on other pages. Preserve the measured counts rather than altering masks or claiming that review reuse means no rendering.

## Deliver and maintain

~~~text
COMMAND_PREFIX recovery/pipeline.py publish --state work/RETURNED.state.json --output ACCEPTED.pdf
~~~

publish writes 交付说明.md inside the task folder and publication.json beside the accepted state, returning their paths and the task_dir. Only the accepted PDF is copied to --output. The note includes source/output hashes, resource deltas, scope, retained issues and recovery instructions. The task folder is inferred from the state parent work/, recovery/ or recovery-vN/; for other layouts specify publish --task-dir DIR containing the state. Notes, record and output conflicts are checked before copying, and replacing existing targets requires --overwrite. Source-size comparison for a sample uses the complete source PDF and is clearly labeled; it is not a same-page compression ratio. Recovery checks verify the frozen dependencies. Run the returned recovery_argv only when rebuilding is needed. It writes work/rebuild/accepted.rebuilt.pdf and sidecars inside the task folder.

pipeline-events.jsonl records command timings and outcomes. Capture exit status, stdout and stderr on failure, then read last-error.json beside --state. Existing targets require explicit --overwrite.
