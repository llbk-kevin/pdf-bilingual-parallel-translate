> Profile scope: default reading tasks follow [practical](practical.md). The strict/low-level details below are consulted as needed, not requirements to exhaust warnings, formula reviews or independent rebuilding in ordinary tasks. Actual viewing evidence remains required.

# In-place translation: default builder and v3 state

## Extract, author, build

Copy scripts/inplace.py and scripts/workflow.py into task recovery when a frozen, independently rebuildable package is needed. Use an existing suitable Python or install requirements.txt in a task environment. No translation service is called by these scripts.

~~~text
python inplace.py extract --source SOURCE --state state.json --pages all
python inplace.py build --source SOURCE --state state.json --output ../work/draft.pdf --pages 1,3-5
~~~

extract creates an authoring inventory, not completed translation. It records the source SHA-256, page count, visible geometry and immutable glyph facts. Native alphabetic spans start unresolved; numeric/symbol-only spans start preserve and still need review. Image/outline text is not automatically recognized. Hidden OCR is marked separately. Check all visible content before setting inventory_reviewed; a page with little native text is not necessarily a page without translation.

Match translations to extract's stable block ID **and source_text**. A separate rawdict/dict extraction with other flags can have different span order and blank-block grouping. Never paste translations by those unrelated block indices. IDs are stable for the same source/extractor, not across arbitrary PDF edits or engine upgrades; the source hash and fresh glyph inventory detect such changes.

The builder reads authoring state without changing it and writes draft.pdf, draft.state.json and draft.font-runs.json. Use the generated state for audit/render: it records actual boxes, font sizes, runtime and builder/dependency hashes, and clears prior qc. Output/report paths are protected against accidental overwrite. Unsupported features and aggregated layout conflicts fail before the candidate PDF is saved. No fallback layout is selected.

## Coordinates and mapping

v3 uses schema_version: 3 and layout.mode: inplace. Each page records source_page (one-based), output_page, geometry (width, height, cropbox, mediabox, rotation, user_unit), source_rect [0,0,W,H], glyphs, blocks, expected_blocks and reading_order. All glyph/source/allowed/cover/actual boxes use **visible page top-left points** after crop, rotation and UserUnit. target_bbox is the actual box shifted right by W into output coordinates. Do not mix PDF bottom-left rectangles with these coordinates.

Each glyph fact includes id, text, bbox, origin, font, size, hidden and trace_type. Do not change these facts to make a layout pass. Zero-width Unicode tails of one ligature retain their original bbox; the builder resolves their removal through the preceding carrier glyph when the font/size/origin/trace facts agree. Keeping one half while replacing the other is rejected. Other unsupported zero-area glyphs fail explicitly rather than being silently omitted.

Each native block references glyph_ids and optional half-open glyph_ranges, e.g. [[0,5],[8,12]]. Every non-whitespace source glyph must belong to exactly one selected range, including preserved formulas and hidden OCR. To merge spans, concatenate their IDs into one coherent block; to keep inline values, split prose and value IDs into separate blocks. Update expected_blocks and reading_order to match the final ordered blocks. Keep source_text/source_bbox and semantic/table/figure anchors meaningful. Use table-cell blocks for in-place table text; the original grid stays intact. A deliberately grouped kind: table also needs the existing source_rows/translated_rows metadata.

The automatic extractor does not decide mathematical semantics. Split and preserve variable names, signs, formula numbers, subscripts and numeric data before replacing adjacent prose. Review every repeated formula. Source issues retain original wording and an explicit treatment.

## Block decisions

| method | Treatment | Required authoring information |
| --- | --- | --- |
| replace | Remove selected **visible native text** on the right and draw translation | glyph IDs/ranges, translation, allowed_bbox, font settings |
| cover | Remove selected hidden/native OCR if supplied; cover the explicit raster/outline label region white and draw black Chinese | cover_bbox (or source_bbox), reason, translation, allowed_bbox; manual labels may have no glyph IDs |
| preserve | Reuse original content without new text or font runs | reason and retained translation/source text |
| unresolved | Keep a recorded outstanding decision | Description/issue; selected builds refuse unresolved blocks |

For an image/outline label add a block with unique id, kind, manually verified source_text/source_bbox, glyph_ids: [], glyph_ranges: [], method: cover, cover_bbox, allowed_bbox, translation, reason and font_size. Keep the cover tight around letters and minimize occlusion. When the user explicitly permits minor local occlusion, record its exact bounds/reason and verify it visually; do not silently obscure meaning-critical data. There is no universal automated proof that a white cover obscures only lettering; visual inspection is required.

Hidden OCR cannot use replace: deleting hidden text alone would leave the visible scanned English unchanged. Use cover with a visible label rectangle, or preserve with a documented reason. Preserve diagram geometry and meaningful symbols around the label. Do not invent native text where the scan is unreadable.

## Fonts, fitting and inline notation

layout.fonts is a registry of {name, source, sha256, purpose, face_index?}; source resolves relative to state. Record acquisition/licensing context in recovery. block.font selects the preferred registry name. A missing character uses a verified registered fallback; an unavailable glyph fails. Original fonts/images are never a reason to ship external runtime dependencies. Chinese fonts are shared across the document and subset after all pages are composed.

font_size is the requested size. Optional font_size_min and font_size_step (default 0.25 pt) permit bounded fitting; without a minimum the size is fixed. Choose a legible per-block minimum after seeing the actual page. The builder records actual_font_size, layout_lines and actual_glyph_boxes. It keeps Latin words/model numbers together where they fit, keeps ordinary closing punctuation with its preceding token, and only splits a token that exceeds a whole line. It does not shorten the text. Overflow reports the block and needed/allowed height.

allowed_bbox defaults to the source box. Extending or moving it requires expansion_reason identifying verified adjacent blank space. Do not move an image, plot frame or table grid to obtain room. The builder measures translated glyph outlines with fontTools (MuPDF glyph_bbox may return a font-wide box), and uses source drawing trace boxes when raw font ascents are inflated. It checks these boxes against preserved native text, other translated glyphs and cover rectangles, rather than rejecting all overlapping allowed boxes. It reports all detected conflicts across the selected pages together. Graphic/background interactions, reading order and readability still require visual review.

rotation supports 0/90/180/270 degrees counterclockwise; extraction preserves source_angle and orthogonal. Non-orthogonal native replacement is rejected; an explicitly designed cover may use a chosen supported orientation. color is RGB [0..1] inherited from native spans (important for white titles on colored backgrounds); cover text is always black. Older authoring blocks without color default to black, so inspect them.

Only balanced, non-nested <sub>…</sub> and <sup>…</sup> markup is supported, e.g. I<sub>out2</sub> or V<sup>2</sup>. They draw at 0.7 times the surrounding size with a baseline offset; actual font runs contain the visible characters, assigned font, size and baseline_shift, not the tags. Other tags fail. Keep complex standalone formulas as source vectors; do not flatten them into ASCII underscores or repeated prose.

The font-run sidecar uses schema_version 1, output_sha256 and runs with page, block, font (registry name), text, font_size, baseline_shift and optional fallback_from. check-fonts excludes preserve blocks from new-draw coverage and verifies actual translated runs. Font coverage alone is not visual acceptance.

## Geometry, resources and interactions

Both panes are placed with show_pdf_page from the **same opened source document**, sharing its graft map. Text redaction is applied only to the right-hand rectangles after both placements, with images=0, graphics=0, text=0 and fill=False. Adjacent center masks are merged only when their union cannot touch preserved glyphs. This leaves image pixels, soft masks, curves, colored fills and table rules in place. Non-image streams are losslessly compressed; source image streams are not re-encoded.

The builder temporarily clears source Rotate and supplies the inverse rotation explicitly to show_pdf_page. Crop/rotation/UserUnit and mixed physical page sizes are tested. PDFium ignores UserUnit, so diagnostic rendering normalizes only an in-memory copy before uniform-scale comparison. The original file is never changed.

show_pdf_page does **not** preserve interactive structures. The builder explicitly copies URI/internal links to both panes with matching destinations, and transfers supported bookmarks. Raw PDF destination modes and null axes are migrated without the lossy get_links representation: XYZ, Fit/H/V/B/BH/BV/R are supported, with rotation-aware axes. Nonfinite bookmark coordinates and link appearance streams require an explicit custom migration and are rejected. An explicitly declared sample records outside-selection links as omitted; other selected-page trials must include internal-link destinations; bookmarks for omitted pages are recorded as omitted, and retained hierarchy is rebased. Full builds keep all supported destinations. Static Highlight, Underline, StrikeOut, Squiggly, Square, Circle, Ink and Stamp annotations with one normal /AP/N stream are copied to both panes as independent annotation objects with their original appearance resources. Crop/UserUnit coordinates are transformed and annotation appearance text is excluded from the translation inventory. This narrow path requires unrotated pages, fully visible annotation rectangles and no actions, popup/reply threads or layers. Text-markup touching replaced text requires a custom translated-anchor appearance and is refused. Other annotations/widgets, attachments, optional-content layers, unsupported link/bookmark actions and text clipping modes 4–7 (including nested Forms) are rejected. Do not silently flatten these features. Other document-level semantics such as tags, scripts, signatures and viewer preferences are outside this builder's preservation claim; inspect relevant originals before choosing a deliberate custom path.

Right-side link hit areas follow actual translated glyphs. A uniquely retained source anchor is located automatically in its affected block; a whole short block belonging to one link can use its actual bounds. Ambiguous anchors require page.link_overrides, e.g. [{"source_link":0,"target_block":"p6-body","target_text":"图3-5","occurrence":1}]. source_link is the zero-based source Link index on that page; occurrence is one-based. Explicit right_bbox or right_bboxes in right-pane-local visible coordinates are also supported. Do not merely shift an original clickable rectangle onto a different reflowed line: an unmapped ambiguous link fails construction. Generated link_mappings record the actual areas; click-check their URI/internal destinations.

Printed source page numbers are already reused on the right; preserve them, including unnumbered covers. Do not add numbers merely because the current trial has fewer pages. For a wholly unnumbered document only, the existing confirmed physical-total pagination fields can add page/total labels inside a reserved upper-right box; they participate in actual font runs and collision checks. For v3 preserve-source pagination, existing artwork supplies the text and no duplicate label is drawn.

## Verification and compatibility

Use check-state, check-fonts, audit and render on generated state. Draft v3 states may contain selected source pages; --final requires the complete source and normal evidence rules. audit restricts a trial's image baseline to selected source pages and remaps destinations. Rendering with state preserves source/output mapping and fingerprints. v1/v2 state readers and historical review records remain supported; do not upgrade acceptance by changing only a version number.

Run the synthetic tests and a representative local document trial after resource/coordinate changes. Test fonts and source PDFs are generated by code; licensed fonts, user PDFs, translated samples and local runtime paths stay outside the repository. See [building.md](building.md) for publication/recovery and the **explicit legacy** builder, and [state-and-qc.md](state-and-qc.md) for final review evidence.

The built state records `annotation_mappings` for migrated static appearances and `redaction_regions` from selected source drawing-trace boxes. Both audit and render check the right pane against the original at the same pixel origin, masking only those source regions, actual translated glyph outline boxes, explicit covers, generated labels and moved visible link borders. A two-pixel raster margin absorbs antialiasing; any remaining pixel above the configured channel tolerance fails (`right_graphics_changed_outside_recorded_regions`). `allowed_bbox` never exempts a whole paragraph from this check. Missing recorded deletion regions fail rather than bypassing the comparison. This check establishes local graphics preservation at the chosen resolution; it does not replace semantic or visual review.

No-action bookmark headings preserve the original outline tree. A null font-size minimum means the fixed requested size.
