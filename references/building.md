> Profile scope: default reading tasks follow [practical](practical.md). The strict/low-level details below are consulted as needed, not requirements to exhaust warnings, formula reviews or independent rebuilding in ordinary tasks. Actual viewing evidence remains required.

# State-driven construction

The default builder is scripts/inplace.py; see [inplace.md](inplace.md) for extraction and v3 authoring. Freeze a copy of it and scripts/workflow.py beside the task state, and record requirements.txt with the actual environment versions. Use build --source, --state and --output explicitly. The builder reads authoring state without modification and emits the PDF, <output>.state.json and <output>.font-runs.json. Use generated state for audit/render: it records actual placement and has cleared qc. Do not replace authored translations with a new extraction when rebuilding.

## Working files and publication

Use <source-stem>/recovery/ for authoring state and builders, and <source-stem>/work/ for candidate PDFs, generated sidecars, extraction, renders and audit reports. Always build inside the working folder: both builders emit sidecars beside their PDFs. Do not build directly to the outer delivery path. Keep 交付说明.md inside <source-stem>/.

After the frozen candidate has passed translation, visual and structural acceptance:

1. Check that the outer <source-stem>_双语左右对照翻译.pdf target does not collide with the original or an existing file. Copy only the accepted PDF, preserving its bytes, and verify its SHA-256 matches the frozen candidate. An unresolved draft stays under work/.
2. Keep current state in recovery/ and supporting reports/evidence within the same working folder. Establish their locations before review when practical; if relocating current state, resolve each relative reference against its old base and re-express it against its new base. Change only paths needed for relocation, preserve semantic data and numeric types, and follow the state-and-qc relocation rules where fingerprinted paths are affected. Do not rewrite historical snapshots or immutable render indices.
3. Point current output.path to the outer PDF, preferably relative to the state file. Keep output hashes and qc unchanged because the PDF bytes are unchanged. Run check-state --final on the current state against the published PDF and retained evidence; record the publication paths and matching hashes in the working folder. Do not claim a new review merely from copying or updating output.path.

The accepted PDF must embed fonts and resources needed for independent reading, rendering, searching and copying. Recovery files are for editing and verification, not runtime dependencies of the PDF. For a delivery-layout check, use a disposable copy, remove only its verified working-folder path, and confirm both PDFs still render and extract the same text. Never delete the user's working folder automatically.

## Default in-place layout

Author v3 decisions with source glyph IDs, method, translation, allowed_bbox, font settings and any explicit cover region. The builder derives target_bbox and actual placement; do not author a second independent page layout. Original table grids and formulas remain in the reused artwork. Group prose semantically, keep cell correspondence and choose bounded fitting only for affected blocks. Source geometry, image sharing, supported links, covers and failure behavior are specified in [inplace.md](inplace.md).

For a cross-document trial, retain a sample-to-original page manifest and original SHA-256 values. Check the original-to-sample chain, including image semantics, links and rendering, not only sample-to-bilingual output. Explicitly record omitted destinations outside the selected pages; do not claim a sample preserves the full document's navigation. Never publish the trial as a complete translation of its source books.

## Explicit legacy example (v1/v2)

Use scripts/example_build.py only when deliberately maintaining an old layout or explicitly requested. Copy it with workflow.py and use requirements-dev.txt. It does not provide the default mirrored artwork and must not be an automatic fallback when in-place construction fails. The following layout details apply to that example only.

Each block needs target_bbox in output top-left points, complete translation and status; a table uses table.translated_rows, with optional col_proportions and spans [x0,y0,x1,y1]. Provide equally shaped source_rows. reading_order lists block IDs. Fonts use name, source path, sha256, purpose and optional face_index; block.font chooses the preferred font. The builder chooses a verified fallback per missing glyph and records the font actually used, including fallback_from. It does not assume that a union of fonts proves the chosen font covers a character. Unsupported font formats remain unverified or fail explicitly.

The example supports ordinary paragraphs, sub/sup markup and real tables on unrotated, uncropped zero-origin pages. It stops on pending blocks, invalid mappings, source overwrite, missing glyphs and overflow. It shares fonts through one document overlay, subsets through ReportLab, compresses content streams and removes unused objects. It deliberately leaves complex math, figure layout, rotation/crop normalization and overlap design to the task builder. Always inspect its output.

The Chinese pane always matches each source page: output size is 2W × H. An existing layout.pane_width_pt is accepted only within 0.1 pt of that page's source width; it cannot widen the pane. Omit it for mixed page widths. The example uses explicit block.font_size and leading; it does not automatically shrink or reflow. Adjust target_bbox/font_size in authoring state after reviewing available space, then rebuild.

Optional explicit pagination uses layout.pagination_strategy and each page.pagination as described in [state-and-qc.md](state-and-qc.md). The example draws the confirmed text right-aligned within its target_bbox and includes it in actual font runs. It does not discover source page numbers or choose positions. Original page-number text belongs to that record, not also to a translated body/footer block; generated labels are layout additions, not invented source text.

## Common font and recovery verification

Run check-fonts OUTPUT.state.json --assignments OUTPUT.font-runs.json --out fonts.json. A custom builder emits the same run shape: schema_version:1, output_sha256 and runs containing page, block, font, text, optional fallback_from. Runs must represent actual draw calls, identify registry font names, and cover every newly drawn block's text and complete translated cells in order. v3 preserve blocks correctly have no new draw runs. Coverage of declared runs is not proof that PDF embedding or glyph display is correct.

For recovery validation, copy state/builder/helper to an independent folder, keep the original external PDF/font dependencies identified, and rebuild there. Change one existing translated block in the copy and, if tables are present, one cell; verify extracted/rendered output changes accordingly and edited input is not reset. A prose-only document does not need a table added for this check. Build the unchanged copy twice and compare bytes/resources; no resources may accumulate. Record dependencies and commands in recovery instructions. Never mutate the accepted package merely to run a test.

Both builders preserve and verify declared layout.inputs. Record the actual interpreter and relevant library versions in recovery; the default builder also records its PyMuPDF version in output state, while the legacy example records its Python, pypdf and ReportLab versions. If cross-environment rebuilding differs in bytes, compare drawing operations, text, resources and renders, and document the precise cause; repeated runs must still be stable. Visual similarity alone cannot excuse unexplained differences.
