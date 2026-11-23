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

Use the [coordination workflow](references/coordination.md) for every PDF. Confirm the agent work table together with filenames: stable names, documents/pages, responsibilities, explicit models/efforts, fresh contexts, dependencies and handoffs. Each document has one state writer and independent review coverage; its translator may also manage merging. Reuse original workers for repairs before creating more. Keep concurrency dynamic; queue when slots are full. Check first-use host capacity, offer changes when needed, and remind the user to fully restart Codex after an approved change. Luna xhigh is the suggested worker model. Verify it with a minimal real probe, not catalog presence; ask before substituting another model after failure.

## Default workflow

When using Node REPL, translators and reviewers register their own kernel before PDF work through coordination session-register; keep the returned exact record path. Keep Node REPL lightweight: query state through frozen pipeline inspect/status, run long commands with the file-backed task_runtime launcher, and view images one at a time. Before a worker finishes or hands off, save its checkpoint, ensure background jobs are supervised, mark its tool session for cleanup and reset its own REPL when supported. The coordinator verifies the old kernel exited; completion or interrupt alone does not prove memory release. See [coordination.md](references/coordination.md) and [practical.md](references/practical.md) for commands.

1. **Check documents; confirm names and agent work plan.** Read [naming.md](references/naming.md) and the coordination workflow at task start. Inspect source and paths read-only, then present both tables in the first confirmation or proposed plan. Obtain confirmation before `prepare`, packaging or productive dispatch; keeping names is valid. Initial boundaries may be provisional until preflight; use prose density, tables, formulas and continued content to assign work before dispatch. One state writer can merge several independent translation patches. Validate the work plan with coordination.py validate-plan; structural checks do not establish approval or model availability. Apply approved renames and verify hashes. On resume reuse decisions; reconfirm only unapproved changes to models, names or destinations.
2. **Preflight.** Discover Python 3.11+ with requirements.txt and a Chinese font. Run `pipeline prepare` with the confirmed source path, requested pages and font. Use its cold-checked command_prefix for subsequent commands, including recovery. It freezes recovery scripts, creates an inventory and reports compatibility blockers before translation. Use the returned commands arrays for an isolated source-render smoke check before workers begin. Inspect source grouping, scans and formula boundaries. Preparation is staged; a failure preserves existing recovery files.
3. **Translate and map.** Read groups.json with its original block boundaries; use edits-template.json as a starting point after checking candidate merges against the source. inspect --detail groups queries current groups by page. Preview representative formula, table or screenshot pages before spreading a layout method. Set readable font_size/font_size_min bounds on representative prose, captions and tables; reuse them for the same text class. Missing bounds mean fixed size. apply saves edits and returns grouped layout_check results; read its details before a preview. build repeats the same layout trial before redaction and reuses it within the build. For zero-leading text resets, the builder isolates the right page Form and separates eligible text objects at the same matrix, preserving native overprints; text clipping, transparency groups, soft masks, patterns and non-opaque contexts remain excluded. Use pipeline apply with batched edits and merge_ids for complete paragraphs. Preserve standalone formulas/identifiers with reasons; keep inline-variable prose coherent, repeating verified short variables in Chinese when needed rather than scattering sentence fragments around original glyphs. Check preserved notation against newly written formulas for duplicate prefixes, and group tables by actual cells rather than fixed x-coordinate thresholds. Check images and outlined text too: zero unresolved blocks does not establish visual coverage. Add only needed local covers; protect numbers, dimensions and neighboring table cells. Use link_overrides_patch for corrections. Confirm inventories after viewing. Save authoring state without manipulating qc; use package baselines and frozen status to resume, and merge through one writer per document. Change prefilled preserve blocks only when their treatment changes.
4. **Build.** Use frozen pipeline build. During adjustments select affected pages and batch similar overflow corrections. Once ready, build the complete requested selection. Always build from source plus authoring state; matching candidates are reused. Read layout_check first; apply’s preview_argv includes only resolved changed pages without layout blockers and is null when none are ready. Fix preview_skipped_pages using preview_blocked_by_page before previewing them; Build reads its source from the saved state. On failure capture exit code, stdout and stderr, then read last-error.json rather than repeating an unchanged command. For preserved_glyph_removed, inspect the source crop and related masks before editing; absent related masks can indicate page-wide normalization. practical preserved_duplicate_reduced requires an explicit retain_right_difference observation after checking the surviving native label; strict still blocks. Do not redraw a label merely to remove this finding. Repeated reports for the same character and position require diagnosis before another attempt. Treat recurring source/state validation failures the same way; do not keep changing font sizes to work around them. Never patch an active frozen runner in place: use refreeze into a new recovery directory and re-export affected packages.
5. **Concentrated check and repair.** Run pipeline verify on generated state: one rendering pass supplies audit and review images plus a fingerprint-bound handoff and empty observation template. Translators check completeness, representative layouts and conflict pages; independent reviewers cover the delivery selection. Do not add a second formal page-by-page review for the translator. Hand the complete machine-checked candidate to its independent reviewer once local repairs are readable. Open each required page at a useful reading scale; zoom only actual concerns. Record actual observations through review. Use `inventory_review_needed` to complete source inventory checks while viewing. Record that confirmation in the observation so the same PDF can reuse its audit and renders. Damaged original, missing pages, major omissions, unreadable Chinese or obscured main figures require repair or explicit affected-part disclosure. Prioritize workflow defects; retain harmless differences with reasons. Do not alter masks to chase zero pixel differences. After edits, repeat verify --previous-state for each relevant prior candidate or reviewed package. Unchanged pages may retain their mechanical evidence and original observations. Expand review only for actual shared dependencies or context changes. When a page needs repair, save observations for the clear pages first and report repairs separately. verify --previous-state can reuse those partial observations.
6. **Deliver.** publish checks frozen inputs/evidence, copies identical PDF bytes and creates resource statistics, hashes and recovery instructions. Ordinary tasks use this recovery consistency smoke check. Independent rebuild/resource stability experiments belong to maintenance or builder/resource changes. Record launches, original-agent continuations, available model evidence and final task status through coordination record; verify registered kernel exits with sessions. Report profile, requested pages, remaining issues and paths honestly; a sample is never a complete-document translation.

## Commands and outputs

Read [practical.md](references/practical.md) for the full edit/observation contract and commands. Put recovery/ and work/ inside each source-stem working folder; publish only the accepted PDF at the chosen destination. Keep PDFs, fonts and artifacts outside the skill repository. Do not delete recovery automatically: it contains saved edits and review evidence.

[inplace.md](references/inplace.md), [state-and-qc.md](references/state-and-qc.md) and [building.md](references/building.md) describe geometry, state and resource checks. Do not separately run audit and render when verify already produced matching evidence. Use v3 in-place state.

Diagnostics retain raw 144 DPI measurements (RGB tolerance 16, changed ratio 0.001). Practical acceptance can retain a reviewed right-side difference; source damage, font failures and coverage errors remain blocking.
