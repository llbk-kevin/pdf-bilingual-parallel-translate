# Layout and translation decisions

## Preserve the page framework

Use visible dimensions after crop, rotation and UserUnit: each W × H source has a W × H Chinese pane and a 2W × H output. Handle mixed sizes page by page, without an added gutter or canvas. The default in-place mode copies the source's images, curves, table rules, backgrounds, columns and page orientation onto the right. These are layout constraints, not empty space to redesign. Inspect the actual document before grouping its text.

Keep existing heading hierarchy, color contrast and header/footer positions. Choose Chinese size from the source text and a readable full-size trial. The audit's 8 pt warning is an investigation cue, not a universal minimum; small original labels and body text need different judgments. Do not add decorative rules, panels or headings to occupy copied artwork.

## Build and translate semantic blocks

Record reading_order and cross-page sentence/table continuations. Work from the default extractor's stable IDs and verified source_text. Merge extraction fragments into coherent passages while retaining their glyph IDs; never map translations by another extractor's block order or collapse a whole page into an unreviewable block. Inventory image-only words, duplicate extraction and invisible OCR separately, with explicit treatment. Keep captions distinct from internal labels and prose references.

Review meaning, tone, negation, conditions and qualifications. Where numerical or mathematical content is present, also check signs, ±, comparisons, proportional/inverse relationships, units and indices; preserve fractions and superscripts/subscripts using [math.md](math.md). For suspected source errors, record the exact quote, page/block, concern and treatment. A necessary nearby note must fit without moving copied artwork; otherwise identify the unresolved interpretation in delivery notes. Supported corrections remain separate from the faithful translation.

Confirm source bounds against rendered pages. Multi-column extraction order is not necessarily reading order. Associate footnotes with their table, references with their section, and definitions with later occurrences. Record figure_id for captions and figure-label blocks. Preserve stable IDs when authoring; new grouped blocks retain a complete source-glyph map.

Keep the glossary small and specific: source term, chosen Chinese term, context and intentionally preserved acronyms. Do not turn conditional claims into unconditional ones. Numeric/unit matching is a cue, not proof: Unicode signs, subscripts and legitimate formatting can defeat naive string comparison. Unreadable OCR needs a retained source snippet and an issue.

## Fit within local constraints

Start in the original paragraph, caption, label or table-cell box. The builder wraps Chinese and supports bounded per-block font fitting; optional font_size_min authorizes a specific lower size, not arbitrary shrinking. Use verified adjacent blank space only when needed, record allowed_bbox and expansion_reason, and retain the source anchor and reading order. Do not move another paragraph, image, plot frame or table grid; do not cross table-cell or column boundaries to borrow room. The copied figure area is occupied, even if a former text-only translation left it blank.

Record actual bounds and font sizes from the builder. Review its aggregated overflow/collision report, then inspect actual rendering: text checks do not prove that a cover or extension avoids important graphical content. Do not lower a whole page/book to its densest block's size, truncate a translation, replace it with a summary, omit a formula or borrow from the left pane. If complete, readable fitting still fails, retain the draft and report the specific unresolved block rather than reverting to the former layout.

## Figures and image labels

Keep each original figure at the same location and size on both sides, sharing its PDF resources. Translate its caption in place. For native text inside the figure, replace only the selected glyphs; preserve numbers, identifiers, units and meaningful symbols. For raster or outlined words, add a bounded white cover and black Chinese text at the label's original position. Review the label visually; OCR/extraction alone is insufficient.

Minimize cover size and occlusion. When the user permits minor local occlusion, record the exact region and reason and inspect it at readable scale; do not silently obscure meaning-critical values or turn a diagram into a broad white panel. Nearby labels may share a small cover when their correspondence remains clear. A label list or summary is not the default substitute for the right-hand figure. Any exceptional treatment remains explicit.

## Tables and formulas

Reuse the original table grid, merged-cell boundaries and line weights. Translate in individual cells, preserving row/column association, header levels, values, symbols, footnotes and continuation labels. Use table-cell blocks with source-glyph/cell mappings; for a grouped kind: table record, keep source_rows and translated_rows with equal shapes and merged-cell metadata. Shape checks do not prove correct cell placement; inspect dense tables enlarged.

Keep every repeated formula and its number as original content when no words need translating. Translate adjacent definitions separately, protecting native variables and their indices. Preserve case, Greek/Latin distinctions, signs, fractions and superscripts/subscripts. In translated prose, use supported sub/sup markup for inline notation; never substitute ASCII underscores or “same as above” for original mathematics. See [inplace.md](inplace.md) for the limited markup and [math.md](math.md) for complex cases.

## Page numbering

Judge printed numbering across the whole original, not just a sample or reader page indices. Copy confirmed source labels in their original positions, including Roman numerals, section prefixes and jumps. The right-hand source artwork already contains them: do not draw duplicate page numbers. Unnumbered covers in a numbered document stay unnumbered. Record unreadable labels rather than guessing.

Only when the complete document has no visible numbering, use the confirmed physical-total policy to add 1/N, 2/N, … at the upper right of the Chinese pane. Reserve a collision-free inset area inside the existing pane. N includes covers and blanks and is never twice the source page count. Do not invent new numbering merely because a trial selects fewer pages. Review values and placement; display labels never replace physical source/output indices in recovery.
