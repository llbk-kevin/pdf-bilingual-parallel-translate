# PDF composition, resources and acceptance

## Geometry and interactive structure

inspect reports MediaBox, CropBox, rotation, UserUnit and physical visible dimensions. PDFium ignores UserUnit; diagnostics normalize an in-memory rendering copy when needed, leaving the original untouched. State coordinates are visible, top-left points after crop/rotation. Raw PDF link rectangles use PDF coordinates; do not mix the two systems.

The default in-place builder places each source page twice with show_pdf_page from the same open source document, then removes only selected native text in the right placement: each source W × H becomes exactly 2W × H. The original pane occupies [0,0,W,H] in visible top-left coordinates. Normalize rotation/crop only with explicit coordinate transforms. Normalize contents, annotations and destinations consistently; changing page boxes alone can reveal formerly clipped material or move content. For nonzero crop origins, test both corners and the left-pane raster against the original. Prevent previously cropped content from leaking into the new right pane. Preserve the original visible clipping region for its content.

show_pdf_page does not migrate annotations or document navigation. The default builder explicitly transfers supported bookmarks and URI/internal links to both panes, preserving raw nullable axes and destination modes with geometry transforms. It rejects unsupported actions, nonfinite bookmark coordinates, link appearance streams, unsupported annotations/widgets, attachments, optional-content layers and nested text-clipping modes. Preserve bookmarks, URI/internal links and their clickable areas. Opening the file successfully does not prove these work. Audit compares link target and raw rectangle conservatively; normalized equivalent coordinates may need manual confirmation. It compares bookmark titles/destination pages, not the full hierarchy or destination zoom. Click representative link types and every flagged destination. Forms, signatures, layers, tags, portfolios, multimedia and JavaScript are outside automatic equivalence checking; inspect any relevant features before claiming preservation. Editing invalidates digital signatures; retain the signed original separately.

Empty-user-password files are opened consistently by inspect, audit, render and state checks. If a password is required, accept only a user-supplied value through --password-env; never guess it or store it in state/logs.

Source and bilingual pages use the same explicit PDFium matrix at dpi/72, with a common pixel origin and source-sized crop. This avoids noninteger-size sampling drift when adding the equally sized right pane. Record renderer/settings and investigate real differences; do not relax tolerances to mask drift.

audit checks the output size against [2W,H] and the source rectangle against [0,0,W,H], with the existing 0.1 pt geometry tolerance. Unequal width/height or a displaced original is an error, with expected and actual geometry reported. Old packages remain readable; rerunning audit applies current geometry rules without rewriting historical acceptance.

## Images, fonts and repeatable generation

Reuse original image streams instead of rasterizing pages or decoding/re-encoding images. Preserve masks, color spaces, Decode arrays and rendering intent. The audit hashes original encoded image payloads and semantic metadata; it compares decoded palette/profile streams to allow equivalent lossless recompression. Equal compressed bytes alone do not establish equivalent display semantics.

The default builder uses images=0, graphics=0, text=0 and fill=False for native text redaction. It keeps diagrams, fills, curves, images and table rules on both panes; white covers are explicit local decisions for raster/outlined labels. It merges small deletion masks only when retained text cannot be touched. Source drawing traces and true translated font outlines avoid font-wide bounding-box false positives; glyph facts remain unchanged. Inspect preserved formulas beside each changed area.

Add Chinese as real Unicode-capable text. Use font coverage appropriate to the document, share each font across pages, and subset using the final glyph set. Verify glyph appearance, selection, copying and extraction; an embedded font or ToUnicode map alone is insufficient. The default in-place builder subsets once after all pages and compresses only non-image streams; applying a generic deflate save to every stream can change original image encodings. The explicit legacy builder uses ReportLab subsetting. Validate final resource signatures and pixels. Never claim cleanup merely because a save call ran.

Run check-fonts against the builder’s actual per-run font assignments, including fallback fonts, before visual review. A union of registered font coverage is insufficient. Unsupported font formats stay unverified.

Regenerate from source plus state after edits. Avoid importing independent page overlays with a fresh full Chinese font on every page. One whole-document overlay can share resources, but inspect the resulting object graph to verify sharing. After any optimizer, save, subset or cleanup, invalidate all old output-bound checks.

## Accounting and interpretation

Inventory follows the reachable object graph, including nested Forms. It counts unique indirect objects and reports incoming graph references. References are graph edges, not a count of drawing operations or page uses. One shared font referenced by many pages contributes its bytes only once.

The report separates encoded font binaries, image streams, Form streams and other reachable streams. The residual is file size minus these streams; it includes dictionaries, cross-reference/object-stream packaging, unused objects or old incremental history and other container overhead. It is an accounting residual, not proof of waste or exact physical byte ownership. The deltas sum to total size change.

Compare duplicate suspects against source hashes and copy counts so existing duplication is not called newly introduced. Same-byte image resources can have different masks or metadata; never delete solely by hash. A new font payload above 5 MiB triggers investigation, not automatic rejection. There is no universal growth-percentage gate. Explain measured changes, investigate large residuals, and maintain legibility and fidelity.

Page content streams are counted by unique referenced objects, separately reporting newly uncompressed streams versus the source baseline. Merging may expand formerly compressed instructions: losslessly compress after merging, then repeat audit and rendering. This is a size diagnosis, not permission to re-encode source images.

## What each check establishes

| Check | Establishes | Still requires review |
| --- | --- | --- |
| Source-pane raster comparison | Appearance within the recorded DPI/tolerances and geometry | Fine detail, layers/interactive behavior and any nonzero differences |
| Source character multiset | Candidate missing/changed visible characters | Reading order, positioning and semantics |
| Right-side CJK extraction/size | Searchability and potentially small text | Correct glyphs, copy order, completeness, clipping and readability |
| Image signatures / resource deltas | Encoded resource changes and new duplicate suspects | Whether changes are intended; masks, profiles and practical fidelity |
| Block/state checks | Internal inventory completeness, table shape and review freshness | Inventory correctness and actual semantic/visual review |
| Render index | Which pages were rendered and the file fingerprint | Which pages were actually opened and checked |

The audit flags twelve or more right-pane pipe separators as a possible flattened table. With a state inventory, only explicit caption blocks participate in figure displacement checks; figure-labels and prose references do not. Without state, unique-figure-number matching remains a heuristic. The displacement cue remains max(36 pt, 10% of source height). Small Chinese is classified by declared block type and actual character position: header/footer-only findings are informational, while other or unknown roles remain warnings. These classifications require a correct inventory and do not establish readability.

Any audit warning needs a page/resource-specific resolution or retained limitation. Mechanical pass alone is never the final acceptance claim.

Static normal-appearance annotations follow the restricted migration contract in [inplace.md](inplace.md): eight common types, independent left/right annotation dictionaries, preserved AP resources, unrotated pages, no actions/reply threads, and no translated-text markup ambiguity. Rendering checks explicitly enable annotations. The in-place audit additionally compares the right pane outside selected source trace boxes, actual translated glyph outlines, covers, labels and visibly moved links. It uses a two-pixel edge margin, never the full allowed layout rectangle, and permits no outside pixel over the channel tolerance. Reports include the mask count, unmasked pixel count and changed outside pixels; render saves a difference PNG on failure.
