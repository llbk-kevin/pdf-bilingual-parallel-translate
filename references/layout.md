# Layout and translation decisions

## Establish a document-specific style

Inspect the actual document before choosing a template. Preserve its major reading zones, columns, hierarchy and page orientation. Choose body size from the original page dimensions, content density and a full-size sample. The audit's 8 pt warning is an investigation cue; recurring headers can be smaller, while dense body text may need more space.

Distinguish the page types actually present, such as prose, data tables, multi-figure pages and landscape pages. Leave a header/footer safe zone instead of placing a new heading over an existing block. Use restrained rules and color that support navigation. No colored rectangle is needed merely to occupy an empty diagram area.

## Build and translate semantic blocks

Record reading_order and cross-page sentence/table continuations. Merge extraction fragments only with a retained source-fragment map; never collapse a whole page into one unreviewable block. Inventory image-only words, duplicate extraction and invisible text separately, explaining inclusion or exclusion. A figure-label list is distinct from a caption or a prose reference.

Review meaning, tone, negation, conditions and qualifications. Where numerical or mathematical content is present, also check signs, ±, comparisons, proportional/inverse relationships, units and indices; preserve fractions and superscripts/subscripts using [math.md](math.md). For suspected source errors, record the exact quote, page/block, concern and treatment. Add a short nearby note for meaning-changing uncertainty; supported suggested corrections remain separate from the translation.

Use stable IDs such as p006-table01 and p014-fig12-caption. Obtain source bounds from extraction and confirm them against the rendered page. Multi-column extraction order is not necessarily reading order. Associate footnotes with the correct table, references with their section, and definitions with later occurrences.

Keep the glossary small and specific: source term, chosen Chinese term, definition/context and any intentionally preserved acronym. Handle proper names and identifiers consistently with the current document and its context. Preserve the scope, certainty and qualifications of claims; do not turn conditional statements into unconditional ones.

Numeric/unit checking is a useful cue, not a proof: equation transformations, Unicode minus signs, subscripts and legitimate number formatting can defeat naive string matching. Compare the actual source and meaning. Unreadable OCR needs a retained source snippet and a recorded issue.

## Fitting without information loss

Use this sequence per block: improve line breaks and Chinese punctuation; adjust sensible column widths and intra-block spacing; move within nearby free space; moderately widen the Chinese pane. Keep all source content at the original scale. Record the chosen pane dimensions, sizes and moved blocks in state.

Do not reduce every page to the densest page's typography. Do not truncate, substitute a summary, silently omit a formula or borrow space from the left pane. If a fixed-height page still fails, mark that page unresolved and report the concrete tradeoff; an incomplete draft is not an accepted final PDF.

## Figures

Apply this section when figures are present. Keep original figures only on the left. Place translated figure number/caption near its counterpart on the right. Translate meaningful internal labels in a compact list keyed by the original label or a precise position, e.g. “upper panel: original label → translated label”. Keep numbers, identifiers and symbols verbatim where appropriate. A summary of a figure is not a substitute for the original figure or its necessary label translations.

Reserve the corresponding vertical space when useful. With multiple figures, split captions and label notes into their own anchors. Do not collect all captions at the top just because that is easy to typeset. Record figure_id in caption and figure-label blocks.

## Tables and formulas

Apply the relevant checks only when the source contains tables or formulas. Preserve header levels, rows, columns, merged-cell relationships, values, symbols, footnotes and continuation labels. Store source_rows and translated_rows as equally shaped cell arrays; record merged cells and footnote anchors as additional metadata. The validator checks array shape and missing cells, not whether drawn grid lines and cell geometry are correct. Inspect the rendered table at readable scale.

Keep each repeated formula and its number. Reuse original notation when it contains no translatable words; translate adjacent definitions and qualifiers. Preserve symbol case, superscripts and subscripts, and distinguish Greek letters from similar Latin letters. Render formulas as text/vector math or reuse the source's vector content when appropriate; never replace repeated equations with “same as above”.
