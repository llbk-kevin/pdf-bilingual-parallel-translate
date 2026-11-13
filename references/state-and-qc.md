# State and review evidence

## State and paths

Use UTF-8 JSON without BOM. [In-place extraction](inplace.md) creates schema_version: 3 with layout.mode: inplace and layout.review_profile set to practical or strict. Use [the pipeline](practical.md) to edit and verify state. Source and output page numbers are one-based. Source boxes use visible top-left points after crop, rotation and UserUnit. The builder records actual right-pane boxes and their output coordinates.

Relative paths resolve from the state file. Keep authoring state and frozen scripts in recovery/, candidates and evidence in work/, and the accepted PDF beside the working folder. Keep the source, fonts and declared layout.inputs available for rebuilding. Each external input has path and sha256. Use lowercase SHA-256 of actual bytes.

Keep each page's expected_blocks and reading_order aligned with the inspected source inventory. Record a reason for pages without translatable content and for preserved blocks. Use table-cell blocks for ordinary in-place tables. Grouped table metadata uses corresponding source_rows and translated_rows. Captions and figure labels identify their figure_id. Store unresolved source concerns with page, block, source_quote, concern and treatment. Supply evidence with a suggested correction.

## Scope and display page labels

The final output maps each page in the declared delivery scope exactly once. A full delivery covers the source document. An explicit sample covers document.selected_source_pages and records omitted destinations. Local preview candidates can cover fewer pages than the declared scope and cannot be published.

The output geometry is 2W × H and the source rectangle is [0,0,W,H]. Printed page labels remain in the reused source artwork. Optional layout.pagination_strategy is preserve-source or physical-total. Each page then records pagination.source_label and pagination.text. Preserve-source uses the confirmed original string or null for an unnumbered page, with empty text for null. Physical-total applies to wholly unnumbered documents, uses null source labels and displays physical source_page/total source page count, including covers and blank pages.

For a generated label add an id, target_bbox in output visible top-left points, font_size and optional font registry name. Reserve a readable box in the right pane before building. Generated labels participate in collision checks and actual font runs. Display labels do not replace the physical page indices.

## Fingerprints and review

content_hash includes source, document, layout, glossary, pages and issues. Output bytes and qc are bound separately. Mechanical evidence is keyed by the candidate and source bytes, comparison state, fonts, assignments and tool versions. Source-inventory acknowledgements and observations are recorded separately. A verified candidate can reuse the existing audit and images after those acknowledgements. Large v3 states use compact UTF-8 JSON and atomic replacement. If a fingerprinted input changes, rebuild and verify from authoring state. Changes to shared fonts, layout, glossary, issues or relevant context can invalidate multiple pages. Practical review uses page-local dependencies plus declared context_pages. Strict review uses the complete document unless context is explicitly reviewed and declared.

verify binds the exact output to the audit, actual font runs, font report and render index. Open review_needed pages and register observations with review. A viewed record binds source page, output hash, index path/hash, settings, image/pixel hashes and page content hash to the actual viewer, time and evidence. A reused record keeps current render hashes plus the original viewed record and a reuse reason. Keep both referenced indices and images. Reuse requires matching pixels, settings and page dependencies. Observation files carry the output and render index SHA-256 from verify. A partially reviewed candidate can supply records through --previous-state. Missing, duplicate or invalid records on one page leave other independently valid records eligible.

check-state --final verifies the declared page coverage, recorded review, font files and assignments, audit dispositions and source/output/builder fingerprints. Explain warnings and retained issues as required by the selected profile. Repair stale inputs at the source and use the review command to save real observations.

## Publish and recover

publish copies the accepted PDF byte for byte and updates output.path while keeping the evidence bound to the same bytes. See [building.md](building.md) for file locations and optional reconstruction. On resume verify the source fingerprint, then load the saved translations, mappings and layout decisions. Set names and paths before preparing the task so the state refers to stable inputs.

The two PDFs embed their reading resources. The working folder holds editable state and review evidence for recovery. If the user discards it, later state checks and evidence reuse require those files to be restored.
