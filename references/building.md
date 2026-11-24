# State-driven construction

Use pipeline prepare to create the complete frozen runtime and v3 state. Run apply, build, verify, review and publish with its returned frozen actions. Build reads saved translations and writes the PDF, state and font assignments; see [inplace.md](inplace.md) for geometry and fields.

## Working files and publication

Use <source-stem>/recovery/ for authoring state and builders, and <source-stem>/work/ for candidate PDFs, generated sidecars, extraction, renders and audit reports. Always build inside the working folder: the builder emits sidecars beside their PDFs. Do not build directly to the outer delivery path. Keep 交付说明.md inside <source-stem>/. Optional rebuilding writes work/rebuild/accepted.rebuilt.pdf and all sidecars inside that folder. pipeline publish returns artifacts.notes and an optional recovery action with these locations; use --task-dir for nonstandard state locations. Ordinary delivery checks recovery dependencies without running a full rebuild.

After the frozen candidate has passed translation, visual and structural acceptance:

1. Use pipeline publish to check target paths and collisions, copy the accepted PDF and verify its SHA-256. Keep drafts in work/.
2. Set source, font, state and evidence paths before building. If a fingerprinted path changes, rebuild and verify as described in [State and review evidence](state-and-qc.md).
3. publish updates output.path, retains the review evidence and rechecks final consistency. It saves the delivery note and publication record in the working folder.

The accepted PDF must embed fonts and resources needed for independent reading, rendering, searching and copying. Recovery files are for editing and verification, not runtime dependencies of the PDF. For a delivery-layout check, use a disposable copy, remove only its verified working-folder path, and confirm both PDFs still render and extract the same text. Never delete the user's working folder automatically.

## Default in-place layout

Author v3 decisions with source glyph IDs, method, translation, allowed_bbox, font settings and any explicit cover region. The builder derives target_bbox and actual placement; do not author a second independent page layout. Original table grids and formulas remain in the reused artwork. Group prose semantically, keep cell correspondence and choose bounded fitting only for affected blocks. Source geometry, image sharing, supported links, covers and failure behavior are specified in [inplace.md](inplace.md).

For a PDF assembled from multiple sources, retain a sample-to-original page manifest and original SHA-256 values. Check the original-to-sample chain, including image semantics, links and rendering. At delivery, list the selected source pages and links omitted because their target pages were not selected.

## Maintainer checks

verify checks actual font runs against the declared registry and drawn text. The run contract is in [inplace.md](inplace.md); ordinary translators do not assemble assignments or a custom builder.

For a recovery experiment, copy the complete task materials into an independent directory, resolve its recorded external PDF/font dependencies, and use the generated accepted-author snapshot and frozen pipeline build command. Change one real translated block (and one table cell if present) through apply, then confirm the extracted/rendered change. Unchanged repeated builds must not accumulate resources. Preserve the accepted task and observations.

The builder checks declared layout.inputs and records its library version. If an intentionally different environment changes output bytes, compare content, resources and pixels and record the concrete cause. GC comparison (--garbage 2 or 4), worker budgets and independent reconstruction belong to maintenance experiments, not ordinary translation.
