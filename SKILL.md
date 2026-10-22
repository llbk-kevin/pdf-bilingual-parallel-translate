---
name: pdf-bilingual-parallel-translate
description: Translate PDFs into Chinese side-by-side versions, preserving the original on the left and reusing complete graphics with in-place Chinese text on the right. Use for translation, layout preservation, and recoverable revisions.
---

# PDF bilingual parallel translation

## Working conventions

Translate with the current session model, without external machine translation. Determine this document's language, domain and audience from its contents. Preserve source and existing outputs. Use UTF-8 without BOM. Read this entry and [practical.md](references/practical.md); other English references are for specific unresolved questions. Maintenance requires AGENTS.md, synchronized Chinese documents and preservation of the resolved CC Switch link.

Default to **practical** reading quality: original intact, requested pages complete, Chinese legible, main text and graphics readable in a standalone PDF. Minor wording, line breaks, tiny residual marks and cosmetic differences may be recorded and delivered. Do not exhaustively correct terminology. Preserve formulas, values, models and pin names directly; never guess from corrupted extraction. Correct an obvious known error safely with the current batch.

Use **strict** only for explicitly requested detailed acceptance. Old states without a profile retain strict semantics; never rewrite historical acceptance. Neither profile imposes fixed time, token or iteration limits. Continue for material blockers or demonstrated workflow defects, not every new cosmetic suggestion.

## Required result

Each requested visible W × H page becomes 2W × H. The left stays at original scale; the right reuses artwork, curves, tables and backgrounds with local Chinese replacement. Translate coherent paragraphs using stable IDs, not isolated lines or unrelated extraction indices. Native glyph facts remain immutable. For scanned or outlined labels use tight recorded white covers. Use source_render_index pixel conversion rather than guessing DPI; compare covered regions with the source so table values and drawing lines remain readable.

Fit in the original paragraph/cell/label, with modest font adjustment and verified adjacent blank space when needed. Never move diagrams or table frames, truncate meaning, guess mathematical characters or silently switch to text-only layout. If a blocker cannot be resolved, retain the draft and identify the affected part.

## Default workflow

1. **Preflight.** Discover Python 3.10+ with requirements.txt and a Chinese font. Run pipeline prepare with original PDF, requested source pages and font. It freezes recovery scripts, creates an inventory and reports risks. Inspect source grouping, scans and formula boundaries. Read naming.md only when naming is needed; renaming originals needs explicit approval.
2. **Translate and map.** Read compact inventory. Use pipeline apply with batched edits and merge_ids for complete paragraphs. Preserve formulas/identifiers with reasons. Add only needed local scan covers. Confirm inventories after actually inspecting visible content. Save authoring state after batches; do not manipulate qc manually.
3. **Build.** Use frozen pipeline build. During adjustments select affected pages and batch similar overflow corrections. Once ready, build the complete requested selection. Always build from source plus authoring state; matching candidates are reused.
4. **Concentrated check and repair.** Run pipeline verify on generated state: one rendering pass supplies audit and review images. Open each required page at a useful reading scale; zoom only actual concerns. Record actual observations through review. Rendering is not viewing. Damaged original, missing pages, major omissions, unreadable Chinese or obscured main figures require repair or explicit affected-part disclosure. Prioritize workflow defects; retain harmless differences with reasons. Do not alter masks to chase zero pixel differences. After edits, verify --previous-state preserves unchanged page reviews and original evidence. Expand review only for actual shared dependencies or context changes.
5. **Deliver.** publish checks frozen inputs/evidence, copies identical PDF bytes and creates resource statistics, hashes and recovery instructions. Ordinary tasks use this recovery consistency smoke check. Independent rebuild/resource stability experiments belong to maintenance or builder/resource changes. Report profile, requested pages, remaining issues and paths honestly; a sample is never a complete-document translation.

## Commands and outputs

Read [practical.md](references/practical.md) for the full edit/observation contract and commands. Put each document's recovery/ and work/ under its output folder; publish only accepted PDF at the chosen destination. Keep PDFs, fonts and artifacts outside the skill repository. Do not delete recovery automatically: it contains saved edits and review evidence.

Low-level inplace.py and pdf_tools.py remain supported; [inplace.md](references/inplace.md), [state-and-qc.md](references/state-and-qc.md) and [building.md](references/building.md) describe strict/manual details. Do not separately run audit and render when verify already produced matching evidence. v1/v2 retain original behavior; example_build.py is explicit legacy compatibility only.

Diagnostics retain raw 144 DPI measurements (RGB tolerance 16, changed ratio 0.001). Practical acceptance can retain a reviewed right-side difference; source damage, font failures and coverage errors remain blocking. Mechanical success is not semantic certification. For workflow evaluation log phase time, tools/builds/renders and rework reasons. Report unavailable token counts as unavailable, not estimates presented as measurements.
