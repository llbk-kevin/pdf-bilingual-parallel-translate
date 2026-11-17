---
name: pdf-bilingual-parallel-translate
description: Translate PDFs into Chinese side-by-side versions, preserving the original on the left and reusing complete graphics with in-place Chinese text on the right. Use for translation, layout preservation, and recoverable revisions.
---

# PDF bilingual parallel translation

## Installation

For a new installation, clone this repository into a supported skills directory as pdf-bilingual-parallel-translate, then install requirements.txt in a Python 3.11+ environment. Use that environment to run scripts/pipeline.py. Supply an available Chinese font at prepare; no font is bundled. Keep outputs outside the skill directory. Existing CC Switch installations must retain their managed link; update the resolved repository instead of replacing the entry. See [practical.md](references/practical.md) for commands and supported inputs. The model translates and reviews pages. The scripts build and check the PDF.

## Working conventions

The coordinator uses the current session model and delegates translation and independent review for every PDF. Determine this document's language, domain and audience from its contents. Preserve source and existing outputs. Use UTF-8 without BOM. Read this entry and [practical.md](references/practical.md); other English references are for specific unresolved questions. Maintenance requires AGENTS.md, synchronized Chinese documents and preservation of the resolved CC Switch link.

Default to **practical** reading quality: original intact, requested pages complete, Chinese legible, main text and graphics readable in a standalone PDF. Minor wording, line breaks, tiny residual marks and cosmetic differences may be recorded and delivered. Do not exhaustively correct terminology. Preserve formulas, values, models and pin names directly; never guess from corrupted extraction. Correct an obvious known error safely with the current batch.

Use **strict** only for explicitly requested detailed acceptance. Record the selected profile in the state. Neither profile imposes fixed time, token or iteration limits. Continue for material blockers or demonstrated workflow defects, not every new cosmetic suggestion.

## Required result

Each requested visible W × H page becomes 2W × H. The left stays at original scale; the right reuses artwork, curves, tables and backgrounds with local Chinese replacement. Translate coherent paragraphs using stable IDs, not isolated lines or unrelated extraction indices. Native glyph facts remain immutable. For scanned or outlined labels use recorded Chinese overlay boxes. Their position must make the source association clear, but practical mode does not require exact erasure, background restoration or matching the original colors. Exposed background, English remnants and minor alignment differences are acceptable when readable; do not rebuild for these alone. Use source_render_index pixel conversion rather than guessing DPI; compare covered regions with the source so table values and drawing lines remain readable.

Fit in the original paragraph/cell/label, with modest font adjustment and verified adjacent blank space when needed. Never move diagrams or table frames, truncate meaning, guess mathematical characters or silently switch to text-only layout. If a blocker cannot be resolved, retain the draft and identify the affected part.

## File locations

Keep the original PDF, accepted bilingual PDF and a folder named after the complete source stem beside one another:

~~~text
documents/
|-- <source-stem>.pdf
|-- <source-stem>_双语左右对照翻译.pdf
`-- <source-stem>/
    |-- 交付说明.md
    |-- recovery/
    `-- work/
        |-- candidates, states, reviews and logs
        `-- rebuild/
            `-- optional rebuilt PDF and its JSON sidecars
~~~

Only the accepted PDF is published outside the working folder. Keep notes and all intermediate files inside it. Ordinary delivery checks recovery dependencies; run recovery_argv only when rebuilding is needed, during maintenance validation or at the user's request. At delivery check this task's created paths against this layout; unrelated pre-existing files need no rearrangement.

## Subagent coordination

Use the [coordination workflow](references/coordination.md) for every PDF. Assign translation and fresh-context independent review tasks per document, adding coherent page tasks for long inputs. Use available subagent slots dynamically and queue work when full. Check first-use host capacity, offer configuration changes when needed, and remind the user to fully restart Codex after an approved change. The coordinator owns naming confirmation, overall decisions and publication. Luna xhigh is the suggested worker model, subject to user choice and availability.

## Default workflow

Keep Node REPL lightweight: query state through frozen pipeline inspect/status, run long commands with the file-backed task_runtime launcher, and view images one at a time. Before a worker finishes or hands off, save its checkpoint, ensure background jobs are supervised, mark its tool session for cleanup and reset its own REPL when supported. The coordinator verifies the old kernel exited; completion or interrupt alone does not prove memory release. See [coordination.md](references/coordination.md) and [practical.md](references/practical.md) for commands.

1. **Check and confirm names.** Read [naming.md](references/naming.md) at the start of every translation task. Inspect the source and existing paths read-only, then present the exact naming table to the user or include it in the proposed plan. Obtain confirmation before `prepare`, packaging or translation dispatch. Apply approved renames and verify PDF hashes, then use the confirmed paths. Keeping the original name is a valid choice. On resume, reuse the recorded decision and reconfirm only affected names or destinations that change.
2. **Preflight.** Discover Python 3.11+ with requirements.txt and a Chinese font. Run `pipeline prepare` with the confirmed source path, requested pages and font. Use its cold-checked command_prefix for subsequent commands, including recovery. It freezes recovery scripts, creates an inventory and reports compatibility blockers before translation. Inspect source grouping, scans and formula boundaries.
3. **Translate and map.** Read compact inventory. Use pipeline apply with batched edits and merge_ids for complete paragraphs. Preserve formulas/identifiers with reasons. Add only needed local scan covers. Treat numbers, dimensions and table cells beside covers as protected; read their exact values before and after at a legible scale. Use link_overrides_patch for individual link corrections. Confirm inventories after actually inspecting visible content. Save authoring state after batches; do not manipulate qc manually. Use package baselines and the frozen `status` command to resume distributed work. Apply ordered packages through one writer per document. Check prefilled preserve blocks against the source and edit them only when their treatment changes.
4. **Build.** Use frozen pipeline build. During adjustments select affected pages and batch similar overflow corrections. Once ready, build the complete requested selection. Always build from source plus authoring state; matching candidates are reused. Use apply’s preview_argv for local corrections; Build reads its source from the saved state. On failure capture exit code, stdout and stderr, then read last-error.json rather than repeating an unchanged command. For preserved_glyph_removed, inspect the source crop and related masks before editing. Repeated reports for the same character and position require diagnosis before another attempt.
5. **Concentrated check and repair.** Run pipeline verify on generated state: one rendering pass supplies audit and review images plus a fingerprint-bound handoff and empty observation template. Hand the complete machine-checked candidate to its independent reviewer once local repairs are readable. Open each required page at a useful reading scale; zoom only actual concerns. Record actual observations through review. Use `inventory_review_needed` to complete source inventory checks while viewing. Record that confirmation in the observation so the same PDF can reuse its audit and renders. Damaged original, missing pages, major omissions, unreadable Chinese or obscured main figures require repair or explicit affected-part disclosure. Prioritize workflow defects; retain harmless differences with reasons. Do not alter masks to chase zero pixel differences. After edits, repeat verify --previous-state for each relevant prior candidate or reviewed package. Unchanged pages may retain their mechanical evidence and original observations. Expand review only for actual shared dependencies or context changes. When a page needs repair, save observations for the clear pages first and report repairs separately. verify --previous-state can reuse those partial observations.
6. **Deliver.** publish checks frozen inputs/evidence, copies identical PDF bytes and creates resource statistics, hashes and recovery instructions. Ordinary tasks use this recovery consistency smoke check. Independent rebuild/resource stability experiments belong to maintenance or builder/resource changes. Report profile, requested pages, remaining issues and paths honestly; a sample is never a complete-document translation.

## Commands and outputs

Read [practical.md](references/practical.md) for the full edit/observation contract and commands. Put recovery/ and work/ inside each source-stem working folder; publish only the accepted PDF at the chosen destination. Keep PDFs, fonts and artifacts outside the skill repository. Do not delete recovery automatically: it contains saved edits and review evidence.

[inplace.md](references/inplace.md), [state-and-qc.md](references/state-and-qc.md) and [building.md](references/building.md) describe geometry, state and resource checks. Do not separately run audit and render when verify already produced matching evidence. Use v3 in-place state.

Diagnostics retain raw 144 DPI measurements (RGB tolerance 16, changed ratio 0.001). Practical acceptance can retain a reviewed right-side difference; source damage, font failures and coverage errors remain blocking.
