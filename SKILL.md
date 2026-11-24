---
name: pdf-bilingual-parallel-translate
description: Translate PDFs into Chinese side-by-side versions, preserving the original on the left and reusing complete graphics with in-place Chinese text on the right. Use for translation, layout preservation, and recoverable revisions.
---

# PDF bilingual parallel translation

Produce a standalone PDF with the original page on the left and its artwork plus local Chinese text on the right, both at the original visible size. Translate coherent paragraphs and individual table cells. Preserve native formulas, values, units and identifiers when appropriate. Keep source glyph facts intact.

Default to **practical**: preserve the original, cover the requested pages, and keep Chinese, tables and main figures readable. Retain harmless remnants, line breaks and cosmetic differences with brief notes. Repair missing content, damaged formulas/values, unreadable text and obstructed main graphics. Use **strict** only when requested. Continue for substantive problems; there are no fixed time, token or agent-count limits.

## Start and roles

The coordinator first reads [naming.md](references/naming.md) and [coordination.md](references/coordination.md), inspects document identity and presents **both exact filenames and the agent work table** for confirmation. Include source, output, working folder, roles/pages, explicit models/efforts and handoff paths. An accepted plan containing these tables is sufficient. Resume confirmed decisions; reconfirm affected items only when the proposed names, destinations or models change. Approved renames and source hash checks precede prepare and translation.

Every PDF has a translator/state writer and a fresh-context independent reviewer. Long documents may have several page owners. Keep concurrency dynamic; reuse original workers for repairs. The coordinator diagnoses skill defects and maintains code.

Read only the material for the assigned role:

- **Coordinator:** [coordination.md](references/coordination.md) — preparation, dispatch, importing completed packages and publishing.
- **Translator:** [practical.md](references/practical.md) — source groups, edits, previews and package delivery.
- **Reviewer:** [review.md](references/review.md) — actual viewing, pass/repair decisions and evidence.
- **Maintainer:** AGENTS.md and [maintenance.md](references/maintenance.md). Geometry and state internals are in [inplace.md](references/inplace.md) and [state-and-qc.md](references/state-and-qc.md).

## Workflow and files

Confirm → prepare → translate/apply → build → verify → independent review → publish. Run the exact action arrays returned by the frozen pipeline. Keep authoring state for edits/builds and candidate state for verification/review/publication. The commands reject the wrong state purpose.

Place only the original and accepted bilingual PDF beside their same-stem task folder:

~~~text
<source-stem>.pdf
<source-stem>_双语左右对照翻译.pdf
<source-stem>/
    交付说明.md
    recovery/                 # authoring state and frozen runtime
    work/                     # packages, candidates, observations and logs
        rebuild/              # optional recovery experiment
~~~

Use UTF-8 without BOM. Save edits through apply, import assigned pages through import-package, and submit real observations through review. Generated templates bind paths and evidence; never hand-edit qc or source glyph facts. Local previews remain inside the task folder. Ordinary publication checks recovery dependencies; rebuilding is a maintenance task or an explicit user request.

## Installation and conditional tools

Install requirements.txt in Python 3.11+ and supply a Chinese font to prepare. No font is bundled. Preserve the managed CC Switch link and maintain its resolved target.

Use short-lived CLI processes for state reads and long logs. If using a persistent Node kernel or unmanaged background work, read [tool-runtime.md](references/tool-runtime.md) for registration, supervised execution and cleanup. Rendering is not an observation; agent completion alone is not proof that a tool kernel exited.
