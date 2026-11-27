# Document identity and naming

Read this reference at the start of every translation task. Apply the TI additions only to confirmed TI documents.

## Identify before naming

Inspect the cover, opening pages, footer and publication/colophon pages for the actual title, publication number and version. Metadata and downloaded filenames are hints only. Retain full title, selected title, Chinese title, identifiers, version, language, vendor when relevant, file role and page/evidence notes in state.document.naming or the task naming manifest.

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

If the user keeps the original filename, derive both the work folder and bilingual filename from that kept stem too; do not independently give only the bilingual PDF a different stem.

## TI additions

Lowercase confirmed TI publication numbers while retaining revision letters, for example SLVA317B becomes slva317b. Read the number from the document, not a reference list. Official Chinese TI documents use an explicit English Document reference for the English number; omit only unavailable number fields. Official Chinese documents do not receive a generated-translation suffix or need retranslation merely for naming.

~~~text
Original: snva168e_Designing A SEPIC Converter_设计 SEPIC 转换器.pdf
Translation: snva168e_Designing A SEPIC Converter_设计 SEPIC 转换器_双语左右对照翻译.pdf
Official Chinese: snvaa43_zhcace2_耦合电感器SEPIC功率级的基本计算.pdf
~~~

## Formatting helper

scripts/workflow.py provides document_filename(source_title, chinese_title, document_id=None, *, role, version=None, source_is_chinese=False, paper=False, vendor=None, english_document_id=None). role is required: original, generated-translation or official-chinese. For Chinese originals set source_is_chinese=True; for papers set paper=True. vendor='TI' enables TI number normalization. The function formats confirmed metadata and returns one filename; it neither identifies documents nor renames files.


~~~python
from workflow import document_filename
original = document_filename('Visitor Information Guide',
    '访客信息指南', 'DOC-012A', role='original')
translated = document_filename('Visitor Information Guide',
    '访客信息指南', 'DOC-012A', role='generated-translation')
~~~

Normalize whitespace and replace Windows-forbidden characters minimally: an English colon becomes a spaced hyphen, and a slash becomes a fullwidth slash. Remove trailing spaces/dots. The helper rejects reserved Windows filenames and components longer than 255 UTF-16 code units without truncation. The agent must additionally check full-path lengths, actual tool support and collisions.

Windows process launch may reject a long working directory even when file I/O supports long paths. Start from a shorter working directory and pass explicit paths for the builder, state, source and output instead of silently shortening confirmed titles.

## Propose, clarify and apply

Inspect the document and existing files read-only. For each document, show a table with role, exact current name, exact proposed name, destination directory, action (keep, rename or create) and reason. Include the source PDF, planned bilingual PDF, source-stem working folder and any existing translation proposed for renaming. Use an empty current-name cell for new items. If the user requests parent directory organization, list any proposed parent directory change in a separate row.

When a proposed name contradicts the actual file role, an identifier's source or version is ambiguous, or a main title would have to be shortened, explain the concrete conflict and ask before deciding the name. Once resolved, use the answer within its stated scope. Do not promote a one-task exception into a standing skill rule without an explicit request.

While confirmation is pending, limit work to read-only checks of the source, paths and official publication information. Present the exact naming table together with the [agent work table](coordination.md) in the first confirmation or proposed execution plan. An accepted plan containing both tables supplies confirmation. The user may keep the existing filename. Save the decision and resume it without asking again. Unapproved model, name or destination changes need confirmation of the affected entries. Ordinary page-boundary and staffing adjustments remain the coordinator’s responsibility.

Before the first plan or confirmation, match the local PDF’s document number and revision to the publisher’s or manufacturer’s official sources. Check the latest verified revision and whether an official Chinese edition exists at that revision. List the local revision, official findings and official links for each document. Say when Chinese is available only in an older revision, when it covers only part of the PDF, or when the version or language could not be verified. Follow an explicit local-only instruction.

If a verified alternative exists, ask which source the user wants alongside the two tables. Otherwise report the findings and list the local PDF as the default input. Offer only available choices: keep the local PDF, use the newer revision for translation, or use the official Chinese edition directly if fully Chinese. For a partly Chinese edition, offer to use it and translate the remaining English. Recommend the latest revision first, then official Chinese at that revision (English Rev C before Chinese Rev B). Follow any explicit revision or language preference.

Confirming the tables alone keeps the supplied PDF. A lookup-only request ends with the findings and leaves local PDFs in place. Switch sources only after the user explicitly selects an official file or asks for the update. Verify the selected file’s official source, document number, revision, page count and SHA-256. Confirm affected filenames and adjust agent page assignments to the selected file before preparation. A fully Chinese official PDF selected for direct use needs neither a generated translation nor translation review.

Before `prepare`, complete approved renames. Record paths and SHA-256, check collisions, directory boundaries and long-path support, then move each group and verify PDF bytes. Save the confirmed table, naming evidence and source SHA-256 in the task naming manifest or state. Use the confirmed paths for `prepare`, packaging and translation. On resume, consult the saved decision and reconfirm only affected entries when a proposed name or destination changes. If a current task input path changes after building, rebuild and verify as described in [State and review evidence](state-and-qc.md).

Preserve existing translations unless their exact deletion was explicitly requested. This naming rule does not authorize deleting old translations.
