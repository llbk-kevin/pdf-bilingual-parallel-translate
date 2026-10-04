# Layout and translation decisions

## Establish a document-specific style

Use the visible source dimensions after crop/rotation: each W × H page has a W × H Chinese pane and a 2W × H output. Handle mixed sizes page by page, with no extra canvas or gutter beyond the two panes. Inspect the actual document before choosing a template. Preserve its major reading zones, columns, hierarchy and page orientation. Choose body size from the original page dimensions, content density and a full-size sample. The audit's 8 pt warning is an investigation cue; recurring headers can be smaller, while dense body text may need more space.

Distinguish the page types actually present, such as prose, data tables, multi-figure pages and landscape pages. Leave a header/footer safe zone instead of placing a new heading over an existing block. Use restrained rules and color that support navigation. No colored rectangle is needed merely to occupy an empty diagram area.

## Build and translate semantic blocks

Record reading_order and cross-page sentence/table continuations. Merge extraction fragments only with a retained source-fragment map; never collapse a whole page into one unreviewable block. Inventory image-only words, duplicate extraction and invisible text separately, explaining inclusion or exclusion. A figure-label list is distinct from a caption or a prose reference.

Review meaning, tone, negation, conditions and qualifications. Where numerical or mathematical content is present, also check signs, ±, comparisons, proportional/inverse relationships, units and indices; preserve fractions and superscripts/subscripts using [math.md](math.md). For suspected source errors, record the exact quote, page/block, concern and treatment. Add a short nearby note for meaning-changing uncertainty; supported suggested corrections remain separate from the translation.

Use stable IDs such as p006-table01 and p014-fig12-caption. Obtain source bounds from extraction and confirm them against the rendered page. Multi-column extraction order is not necessarily reading order. Associate footnotes with the correct table, references with their section, and definitions with later occurrences.

Keep the glossary small and specific: source term, chosen Chinese term, definition/context and any intentionally preserved acronym. Handle proper names and identifiers consistently with the current document and its context. Preserve the scope, certainty and qualifications of claims; do not turn conditional statements into unconditional ones.

Numeric/unit checking is a useful cue, not a proof: equation transformations, Unicode minus signs, subscripts and legitimate number formatting can defeat naive string matching. Compare the actual source and meaning. Unreadable OCR needs a retained source snippet and a recorded issue.

## Fitting without information loss

Fit dynamically within the fixed Chinese pane. Combine line breaks, column widths, leading and paragraph spacing with modest expansion into nearby page-edge, upper/lower or unused figure-area space, and reduce only affected blocks’ font sizes as needed. Choose the combination for the actual page rather than following a rigid sequence. Stay near corresponding source blocks and preserve reading order, safe margins, figure anchors and page-number space. Record final bounds, actual sizes and reasons for moved blocks in state.

Do not impose one minimum font size or reduce a whole page/book to its densest block’s typography. Do not truncate, substitute a summary, silently omit a formula or borrow space from the left pane. Keep the original at 1:1 and never widen either pane or increase output height. If readable, complete fitting still fails, mark that page unresolved and report the concrete tradeoff; an incomplete draft is not an accepted final PDF.

## Figures

Apply this section when figures are present. Keep original figures only on the left. Place translated figure number/caption near its counterpart on the right. Translate meaningful internal labels in a compact list keyed by the original label or a precise position, e.g. “upper panel: original label → translated label”. Keep numbers, identifiers and symbols verbatim where appropriate. A summary of a figure is not a substitute for the original figure or its necessary label translations.

Reserve the corresponding vertical space when useful; it is not an untouchable exclusion zone. Space left by not repeating pictures, plots or diagrams on the right may accommodate nearby translation, provided captions/labels remain unambiguous. Data tables still retain their rows and columns. With multiple figures, split captions and label notes into their own anchors. Do not collect all captions at the top just because that is easy to typeset. Record figure_id in caption and figure-label blocks.

## Tables and formulas

Apply the relevant checks only when the source contains tables or formulas. Preserve header levels, rows, columns, merged-cell relationships, values, symbols, footnotes and continuation labels. Store source_rows and translated_rows as equally shaped cell arrays; record merged cells and footnote anchors as additional metadata. The validator checks array shape and missing cells, not whether drawn grid lines and cell geometry are correct. Inspect the rendered table at readable scale.

Keep each repeated formula and its number. Reuse original notation when it contains no translatable words; translate adjacent definitions and qualifiers. Preserve symbol case, superscripts and subscripts, and distinguish Greek letters from similar Latin letters. Render formulas as text/vector math or reuse the source's vector content when appropriate; never replace repeated equations with “same as above”.

## Page numbering

Judge visible page numbering across the whole document before composing pages; reader page indices and PDF page-label metadata alone do not establish printed numbering. Preserve confirmed original labels and their corresponding Chinese-pane positions, including Roman numerals, section prefixes and jumps. In an already numbered document, leave covers or other unnumbered pages unnumbered. Preserve an unreadable label as an issue rather than guessing.

Only when no page has visible numbering, add physical-page/total labels (1/N, 2/N, …) at the upper right of each Chinese pane. N is the number of input PDF pages, including covers and blanks, never twice that number. Reserve an inset area within the existing pane before laying out nearby text; do not cover headings, captions or body text. Review values, location and overlap on every final page. Display labels never replace the one-based physical source/output indices used in recovery.
