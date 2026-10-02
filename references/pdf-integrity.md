# PDF composition, resources and acceptance

## Geometry and interactive structure

inspect reports MediaBox, CropBox, rotation, UserUnit and PDFium's visible dimensions. State coordinates are visible, top-left points after crop/rotation. Raw PDF link rectangles use PDF coordinates; do not mix the two systems.

Prefer cloning the original document and expanding each page's visible region to the right. Normalize rotation/crop only with explicit coordinate transforms. Normalize contents, annotations and destinations consistently; changing page boxes alone can reveal formerly clipped material or move content. For nonzero crop origins, test both corners and the left-pane raster against the original. Prevent previously cropped content from leaking into the new right pane. Preserve the original visible clipping region for its content.

Preserve bookmarks, URI/internal links and their clickable areas. Opening the file successfully does not prove these work. Audit compares link target and raw rectangle conservatively; normalized equivalent coordinates may need manual confirmation. It compares bookmark titles/destination pages, not the full hierarchy or destination zoom. Click representative link types and every flagged destination. Forms, signatures, layers, tags, portfolios, multimedia and JavaScript are outside automatic equivalence checking; inspect any relevant features before claiming preservation. Editing invalidates digital signatures; retain the signed original separately.

## Images, fonts and repeatable generation

Reuse original image streams instead of rasterizing pages or decoding/re-encoding images. Preserve masks, color spaces, Decode arrays and rendering intent. The audit hashes original encoded image payloads and semantic metadata; it compares decoded palette/profile streams to allow equivalent lossless recompression. Equal compressed bytes alone do not establish equivalent display semantics.

Add Chinese as real Unicode-capable text. Use font coverage appropriate to the document, share each font across pages, and subset using the final glyph set. Verify glyph appearance, selection, copying and extraction; an embedded font or ToUnicode map alone is insufficient. The diagnostic dependencies do not perform font subsetting. Choose a builder that subsets fonts (for example a suitable ReportLab TrueType workflow) or a separately available optimizer and validate its result. Never claim cleanup merely because a save call ran.

Regenerate from source plus state after edits. Avoid importing independent page overlays with a fresh full Chinese font on every page. One whole-document overlay can share resources, but inspect the resulting object graph to verify sharing. After any optimizer, save, subset or cleanup, invalidate all old output-bound checks.

## Accounting and interpretation

Inventory follows the reachable object graph, including nested Forms. It counts unique indirect objects and reports incoming graph references. References are graph edges, not a count of drawing operations or page uses. One shared font referenced by many pages contributes its bytes only once.

The report separates encoded font binaries, image streams, Form streams and other reachable streams. The residual is file size minus these streams; it includes dictionaries, cross-reference/object-stream packaging, unused objects or old incremental history and other container overhead. It is an accounting residual, not proof of waste or exact physical byte ownership. The deltas sum to total size change.

Compare duplicate suspects against source hashes and copy counts so existing duplication is not called newly introduced. Same-byte image resources can have different masks or metadata; never delete solely by hash. A new font payload above 5 MiB triggers investigation, not automatic rejection. There is no universal growth-percentage gate. Explain measured changes, investigate large residuals, and maintain legibility and fidelity.

## What each check establishes

| Check | Establishes | Still requires review |
| --- | --- | --- |
| Source-pane raster comparison | Appearance within the recorded DPI/tolerances and geometry | Fine detail, layers/interactive behavior and any nonzero differences |
| Source character multiset | Candidate missing/changed visible characters | Reading order, positioning and semantics |
| Right-side CJK extraction/size | Searchability and potentially small text | Correct glyphs, copy order, completeness, clipping and readability |
| Image signatures / resource deltas | Encoded resource changes and new duplicate suspects | Whether changes are intended; masks, profiles and practical fidelity |
| Block/state checks | Internal inventory completeness, table shape and review freshness | Inventory correctness and actual semantic/visual review |
| Render index | Which pages were rendered and the file fingerprint | Which pages were actually opened and checked |

The audit also flags twelve or more right-pane pipe separators as a possible flattened table, and uniquely matched figure numbers displaced vertically by more than max(36 pt, 10% of source height). These are review cues, not semantic judgments; references within prose may also match.

Any audit warning needs a page/resource-specific resolution or retained limitation. Mechanical pass alone is never the final acceptance claim.
