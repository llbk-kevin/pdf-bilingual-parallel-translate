# Translator workflow

Read the skill entry and this page. Use the assigned source, authoring state, groups and edit template. The coordinator has confirmed names and models. Do not change the skill or another page owner's state.

## Translate

1. Inspect the source at a readable scale, including image/outlined labels. groups.json is a source view; edits-template.json contains conservative candidates. Confirm paragraph and cell boundaries before merging. A zero pending-block count does not establish image-text coverage.
2. Translate representative prose, formula, table or screenshot blocks first. Confirm readable font_size/font_size_min bounds and local blank space. Preserve standalone formulas and identifiers with reasons. Compose inline-variable prose coherently, repeating verified short symbols/values when needed.
3. Write work/edits.json (package: edits.json beside its state), then run the returned apply action. Read the summary and details for affected pages. Legal translations and merges remain saved even when layout needs repair. Subsequent files contain only incremental edits to current IDs; do not resubmit the whole initial template or its merge_ids.
4. Batch edits to similar prose once a representative layout is readable. When first trying a complex layout, changing which block owns formula or table text, or repairing a redaction collision, preview the affected pages from the latest authoring state before handoff. Use the returned build and verify actions and view the images in render_index.

Use the returned frozen command arrays, not a reconstructed shell prefix. To read current IDs, use inspect with explicit pages and detail groups/blocks; glyph details also require a block. The result is bounded and supports offset/limit.

## Edit format

~~~json
{"blocks":[{"page":1,"id":"CURRENT_SOURCE_ID","method":"replace","translation":"中文","font_size":9,"font_size_min":8}]}
~~~

Use current IDs. An initial merge supplies merge_ids with all complete source blocks; subsequent edits use only the merged ID. The template does not recommend uncertain cross-column merges. An explicit source separator prevents merging text across it. For an incorrect merge:

~~~json
{"blocks":[{"page":1,"id":"MERGED_ID","split":true}]}
~~~

split restores complete source spans, returns current IDs through inspect and keeps the old translation in page split_notes. The restored text must be mapped again. Do not modify source glyphs or splice page JSON.

Methods: replace for visible native text; preserve with reason for formulas/values/already-Chinese text; cover with reason for image, outline or OCR text. A cover supplies source_bbox, allowed_bbox and optionally cover_bbox, cover_fill and cover_text_color. Its association must be clear; practical permits visible English remnants or different colors. Compare new covers with lines, arrows, table values and labels.

Keep text inside its paragraph/cell. Use allowed_bbox plus expansion_reason only for verified adjacent blank space. Do not borrow across cells or keep shrinking text until a warning disappears. Fields for unusual geometry are documented in [inplace.md](inplace.md).

Apply checks layout, protected-text collisions and links together. Read existing diagnostics once before changing the edit. Simple unique Figure N → 图 N links are located automatically; unresolved anchors require a page link_overrides_patch entry specifying source_link and target_block/target_text/occurrence, or a verified right_bbox. The source destination is preserved.

## Package delivery and repairs

Edit the package's authoring state through ordinary apply. Deliver its directory, plus a separate note of remaining substantive issues and any cross-page context. The coordinator imports its current result, maintains the shared glossary and collects delivery remarks.

After import, further repairs use a newly exported affected page range and the same translator where possible. Source or baseline conflicts go to the coordinator. A successful machine check does not replace independent review.

The independent reviewer checks the complete delivery candidate. Once a candidate is handed over, wait for substantive findings before changing it. Record harmless practical differences in the handoff.

For persistent Node kernels or background jobs, use [tool-runtime.md](tool-runtime.md); direct CLI work does not require kernel registration.
