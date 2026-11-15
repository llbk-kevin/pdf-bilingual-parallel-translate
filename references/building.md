# State-driven construction

Use pipeline prepare to create the complete frozen runtime and v3 state. Run apply, build, verify, review and publish with its command_prefix/runner. Build reads saved translations and writes the PDF, state and font assignments; see [inplace.md](inplace.md) for geometry and fields.

## Working files and publication

Use <source-stem>/recovery/ for authoring state and builders, and <source-stem>/work/ for candidate PDFs, generated sidecars, extraction, renders and audit reports. Always build inside the working folder: the builder emits sidecars beside their PDFs. Do not build directly to the outer delivery path. Keep 交付说明.md inside <source-stem>/. Optional rebuilding writes work/rebuild/accepted.rebuilt.pdf and all sidecars inside that folder. pipeline publish returns notes and recovery_argv with these locations; use --task-dir for nonstandard state locations. Ordinary delivery checks recovery dependencies without running a full rebuild.

After the frozen candidate has passed translation, visual and structural acceptance:

1. Use pipeline publish to check target paths and collisions, copy the accepted PDF and verify its SHA-256. Keep drafts in work/.
2. Set source, font, state and evidence paths before building. If a fingerprinted path changes, rebuild and verify as described in [State and review evidence](state-and-qc.md).
3. publish updates output.path, retains the review evidence and rechecks final consistency. It saves the delivery note and publication record in the working folder.

The accepted PDF must embed fonts and resources needed for independent reading, rendering, searching and copying. Recovery files are for editing and verification, not runtime dependencies of the PDF. For a delivery-layout check, use a disposable copy, remove only its verified working-folder path, and confirm both PDFs still render and extract the same text. Never delete the user's working folder automatically.

## Default in-place layout

Author v3 decisions with source glyph IDs, method, translation, allowed_bbox, font settings and any explicit cover region. The builder derives target_bbox and actual placement; do not author a second independent page layout. Original table grids and formulas remain in the reused artwork. Group prose semantically, keep cell correspondence and choose bounded fitting only for affected blocks. Source geometry, image sharing, supported links, covers and failure behavior are specified in [inplace.md](inplace.md).

For a PDF assembled from multiple sources, retain a sample-to-original page manifest and original SHA-256 values. Check the original-to-sample chain, including image semantics, links and rendering. At delivery, list the selected source pages and links omitted because their target pages were not selected.

## Common font and recovery verification

Run check-fonts OUTPUT.state.json --assignments OUTPUT.font-runs.json --out fonts.json. A custom builder emits the same run shape: schema_version:1, output_sha256 and runs containing page, block, font, text, optional fallback_from. Runs must represent actual draw calls, identify registry font names, and cover every newly drawn block's text and complete translated cells in order. v3 preserve blocks correctly have no new draw runs. Inspect glyph display in the rendered output.

For recovery validation, copy state/builder/helper to an independent folder, keep the original external PDF/font dependencies identified, and rebuild there. Change one existing translated block in the copy and, if tables are present, one cell; verify extracted/rendered output changes accordingly and edited input is not reset. A prose-only document does not need a table added for this check. Build the unchanged copy twice and compare bytes/resources; no resources may accumulate. Record dependencies and commands in recovery instructions. Never mutate the accepted package merely to run a test.

The builder verifies declared layout.inputs and records the PyMuPDF version in generated state. Record the interpreter and relevant library versions for recovery. If cross-environment rebuilding differs in bytes, compare drawing operations, text, resources and renders, and document the precise cause; repeated runs must still be stable. Visual similarity alone cannot excuse unexplained differences.
