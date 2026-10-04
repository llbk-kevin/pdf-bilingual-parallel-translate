# Mathematical notation and source uncertainty

Use true subscript/superscript positioning and preserve Greek/Latin case, minus, plus/minus, approximate/equality relations and equation numbers. Avoid Unicode subscript characters when the font lacks them: position the normal glyph as a subscript instead. Never substitute an approximate relation with equality merely to avoid a missing glyph.

Short inline fractions may use a slash when unambiguous. Preserve stacked fractions, grouping, roots and aligned multiline structure when flattening would obscure scope or correspondence. Break long equations at meaningful operators; keep their number and repeated occurrences. Use text/vector math or an appropriate source vector fragment; do not rasterize formulas as a generic fallback. The minimal builder supports sub/sup markup only; complex fractions need task-specific drawing.

Inventory formulas separately from adjacent prose. Compare symbols, exponents, sign, units and qualifiers against a zoomed source. Read definitions before selecting translated variable names. Check typical versus guaranteed values, bounds and proportional/inverse wording as explicit semantic items; number-string matching is only a clue.

When the source appears wrong, preserve its literal claim and add a short local note. Record page, block, source_quote, concern and treatment; suggested_correction and evidence are optional and coupled. For example, a sentence says proportional while its equation is inverse: preserve the sentence's claim, flag the discrepancy, and keep the actual equation. Do not silently replace the claim. Historical standards and links remain historical unless a separate update was requested.
