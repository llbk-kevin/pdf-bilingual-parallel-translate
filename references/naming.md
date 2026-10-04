# Document identity and TI naming

## Identify before naming

Inspect the first pages and footer for this publication's number (for example SLUP339, SLVA317B, SNVA168E), retaining revision letters and lowercasing the identifier. Read the visible cover title; metadata and filenames are hints only. Do not use a cited publication, device or reference-design number. Continue through relevant pages if the number is absent; omit unconfirmed fields rather than guessing. Keep full title, selected title, Chinese title, number, vendor, source_kind and page/evidence notes in state.document.naming. Long subtitles may be omitted; preserve main-title meaning and English capitalization.

TI English originals AND generated bilingual outputs:

~~~text
<number>_<English title>_<Chinese title>_双语左右对照翻译.pdf
snva168e_Designing A SEPIC Converter_设计 SEPIC 转换器_双语左右对照翻译.pdf
~~~

They have the same basename but different paths: original beside the task folder, translated PDF inside it. source/output identity is established by content and hashes, never that suffix. Append the suffix once. No number means English title + Chinese title + suffix.

Official Chinese TI documents:

~~~text
<English number>_<Chinese number>_<official Chinese title>.pdf
snvaa43_zhcace2_耦合电感器SEPIC功率级的基本计算.pdf
~~~

Use an explicit English Document reference for the English number. Omit only missing fields. Do not append a generated-translation suffix or retranslate an official Chinese document merely because of naming work.

## Propose and apply

Proactively present old path, new path, role and reason for TI naming changes. Normal mode requires user confirmation of the actual table before renaming. In Plan mode include the exact table; executing the accepted plan needs no second confirmation. Translation can continue independently while a naming decision is pending. New outputs use the chosen naming rule without another approval flow.

Normalize title line breaks and confirmed line-break hyphenation. Retain the complete title as metadata. Replace Windows-forbidden characters minimally (colon becomes spaced hyphen, slash becomes fullwidth slash); remove trailing spaces/dots. scripts/workflow.py ti_filename implements formatting of already verified metadata; it does not discover authoritative IDs or rename files. Check full-path length in the target environment. Do not silently truncate a title or append a random counter when a target collides: show a corrected table.

Apply exact paths, never broad rename patterns. Check source/output hashes, collisions and actual resolved directory boundaries before moves. Rename the task folder to the original's stem and update active recovery paths, instructions, queue and index. Preserve immutable historical reports and old review evidence. A path-only migration may retain old acceptance using a fingerprinted previous-state snapshot and a migration record; any content or builder change requires ordinary invalidation. Old states stay version 1 unless the new evidence is actually collected.

The default is to preserve existing translations. Deletion requires a concrete user instruction and exact targets; a one-time cleanup must not become a universal skill rule. Non-TI naming follows user preference without applying TI numbering.
