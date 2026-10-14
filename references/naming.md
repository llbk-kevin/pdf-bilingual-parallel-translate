# Document identity and naming

Read this reference before naming any source, bilingual output or task directory. Apply the TI additions only to confirmed TI documents.

## Identify before naming

Inspect the cover, opening pages, footer and publication/colophon pages for the actual title, publication number and version. Metadata and downloaded filenames are hints only. Retain full title, selected title, Chinese title, identifiers, version, language, vendor when relevant, file role and page/evidence notes in state.document.naming or the task naming manifest. For historical accepted states, keep new naming evidence in the migration manifest instead of changing fingerprinted content.

Use the actual original-language title, including non-English titles; do not manufacture an English intermediate title. Preserve capitalization and model names that belong to the title. Join line breaks and confirmed line-break hyphenation. An overlong subtitle may be omitted, with the complete title retained as evidence; do not silently remove main-title meaning.

A publication number must identify this document. Do not substitute a device model, cited publication, reference design, date or numbers concatenated in a download filename. Non-TI identifiers retain official spelling, including digits and hyphens. Missing unconfirmed numbers are omitted with their separators. Papers omit the number field even when an article number or DOI exists; keep those identifiers in the evidence.

## Formats and file roles

| Role | Filename |
| --- | --- |
| Non-Chinese original | `<number>_<original title>_<Chinese title><optional version>.pdf` |
| Generated bilingual translation | `<number>_<original title>_<Chinese title><optional version>_双语左右对照翻译.pdf` |
| Chinese original or general official Chinese document | `<number>_<Chinese original title><optional version>.pdf` |
| Official Chinese TI document | `<English number>_<Chinese number>_<official Chinese title><optional version>.pdf` |

Omit absent number fields. Chinese originals contain the title only once. Append a confirmed version to the Chinese title in fullwidth parentheses, such as （Rev1.7） or （V3.5）; dates do not automatically become versions. Keep an already present identical version once. Only generated bilingual output receives the translation suffix, once. Establish roles from actual content and provenance before correcting misleading old suffixes.

The original, accepted translation and working folder sit beside one another. The working folder uses the complete source filename stem without an extra suffix; the accepted PDF uses that stem plus the translation suffix. All per-document supporting files and drafts remain inside the working folder. Honor explicitly selected destination directories. Never overwrite the source or an existing target.

## TI additions

Lowercase confirmed TI publication numbers while retaining revision letters, for example SLVA317B becomes slva317b. Read the number from the document, not a reference list. Official Chinese TI documents use an explicit English Document reference for the English number; omit only unavailable number fields. Official Chinese documents do not receive a generated-translation suffix or need retranslation merely for naming.

~~~text
Original: snva168e_Designing A SEPIC Converter_设计 SEPIC 转换器.pdf
Translation: snva168e_Designing A SEPIC Converter_设计 SEPIC 转换器_双语左右对照翻译.pdf
Official Chinese: snvaa43_zhcace2_耦合电感器SEPIC功率级的基本计算.pdf
~~~

## Formatting helper

scripts/workflow.py provides document_filename(source_title, chinese_title, document_id=None, *, role, version=None, source_is_chinese=False, paper=False, vendor=None, english_document_id=None). role is required: original, generated-translation or official-chinese. For Chinese originals set source_is_chinese=True; for papers set paper=True. vendor='TI' enables TI number normalization. The function formats confirmed metadata and returns one filename; it neither identifies documents nor renames files.

The TI wrapper ti_filename(english_title, chinese_title, document_id=None, *, role, english_document_id=None, version=None) now also requires role. Replace old implicit-role calls and the former official_chinese boolean with an explicit role. A missing role fails rather than choosing a suffix silently.

~~~python
from workflow import document_filename
original = document_filename('Eight Hints for Better Scope Probing',
    '改善示波器探测的八项提示', '5989-7894EN', role='original')
translated = document_filename('Eight Hints for Better Scope Probing',
    '改善示波器探测的八项提示', '5989-7894EN', role='generated-translation')
~~~

Normalize whitespace and replace Windows-forbidden characters minimally: an English colon becomes a spaced hyphen, and a slash becomes a fullwidth slash. Remove trailing spaces/dots. The helper rejects reserved Windows filenames and components longer than 255 UTF-16 code units without truncation. The agent must additionally check full-path lengths, actual tool support and collisions.

Windows process launch may reject a long working directory even when file I/O supports long paths. Start from a shorter working directory and pass explicit paths for the builder, state, source and output instead of silently shortening confirmed titles.

## Propose, clarify and apply

For every document, proactively check names before translation and present an exact before/after table for the source, any existing output being renamed, and the task directory, with roles and reasons. Normal mode requires confirmation of that table. An accepted Plan containing the table needs no second confirmation. Translation may continue independently while naming is pending. New outputs follow the selected format without another rename approval.

When a proposed name contradicts the actual file role, an identifier's source or version is ambiguous, or a main title would have to be shortened, explain the concrete conflict and ask before deciding the name. Once resolved, use the answer within its stated scope. Do not promote a one-task exception into a standing skill rule without an explicit request.

Before moves, save exact paths and fingerprints, check collisions and resolved directory boundaries, and verify long-path support in an isolated fixture where needed. Move one group at a time with a durable checkpoint; do not use broad wildcard renames or silently overwrite targets. Update current recovery paths, regeneration instructions, queue and delivery index. Preserve original audit/review bytes and each earlier migration snapshot, following [state-and-qc.md](state-and-qc.md). Verify PDFs remain byte-identical and test rebuilding only in independent copies. Keep clearly identified historical records out of bulk path replacements.

Preserve existing translations unless their exact deletion was explicitly requested. This naming rule does not authorize deleting old translations.
