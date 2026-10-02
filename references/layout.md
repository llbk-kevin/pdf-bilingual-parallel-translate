# Layout and translation decisions

## Establish a document-specific style

Inspect the actual document before choosing a template. Preserve its major reading zones, columns, hierarchy and page orientation. Start with body text around 9–11 pt for an ordinary manual, then adjust from the original and a full-size sample. These are starting points, not universal minima. The audit's 8 pt warning is an investigation cue; recurring headers can be smaller, while dense body text may need more space.

Treat body text, parameter tables, multi-figure pages and landscape slides as separate page types. Leave a header/footer safe zone instead of placing a new heading over an existing block. Use restrained rules and color that support navigation. No colored rectangle is needed merely to occupy an empty diagram area.

## Build and translate semantic blocks

Use stable IDs such as p006-table01 and p014-fig12-caption. Obtain source bounds from extraction and confirm them against the rendered page. Multi-column extraction order is not necessarily reading order. Associate footnotes with the correct table, references with their section, and definitions with later occurrences.

Keep the glossary small and specific: source term, chosen Chinese term, definition/context and any intentionally preserved acronym. Preserve vendor names and part numbers; vendor-specific wording only applies to relevant source documents. Translate conditions as conditions, not unconditional specifications. Distinguish maximum ratings from recommended operating conditions and typical values from guaranteed limits.

Numeric/unit checking is a useful cue, not a proof: equation transformations, Unicode minus signs, subscripts and legitimate number formatting can defeat naive string matching. Compare the actual source and meaning. Unreadable OCR needs a retained source snippet and a recorded issue.

## Fitting without information loss

Use this sequence per block: improve line breaks and Chinese punctuation; adjust sensible column widths and intra-block spacing; move within nearby free space; moderately widen the Chinese pane. Keep all source content at the original scale. Record the chosen pane dimensions, sizes and moved blocks in state.

Do not reduce every page to the densest page's typography. Do not truncate, substitute a summary, silently omit a formula or borrow space from the left pane. If a fixed-height page still fails, mark that page unresolved and report the concrete tradeoff; an incomplete draft is not an accepted final PDF.

## Figures

Keep original figures only on the left. Place translated figure number/caption near its counterpart on the right. Translate meaningful internal labels in a compact list keyed by the original label or a precise position, e.g. “upper trace: input voltage”. Keep numbers, net names and variable-only labels verbatim where appropriate. A circuit description is not a substitute for the original figure or a literal label translation.

Reserve the corresponding vertical space when useful. With multiple figures, split captions and label notes into their own anchors. Do not collect all captions at the top just because that is easy to typeset. Record figure_id in caption and figure-label blocks.

## Tables and formulas

Preserve header levels, rows, columns, merged-cell relationships, values, symbols, footnotes and continuation labels. Store source_rows and translated_rows as equally shaped cell arrays; record merged cells and footnote anchors as additional metadata. The validator checks array shape and missing cells, not whether drawn grid lines and cell geometry are correct. Inspect the rendered table at readable scale.

Keep each repeated formula and its number. Reuse original notation when it contains no translatable words; translate adjacent definitions and qualifiers. Preserve symbol case, superscripts and subscripts, and distinguish Greek letters from similar Latin letters. Render formulas as text/vector math or reuse the source's vector content when appropriate; never replace repeated equations with “same as above”.

## Local regression page types

The development references included a double-column first page, a dense parameter table, a multi-caption page and a formula page from NSI826x; circuit explanation pages from NSI8608; and landscape tables/complex diagrams from the flyback presentation. They motivate these rules, not a fixed template. Actual PDFs and their translations remain outside the repository.
