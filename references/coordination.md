# Coordinating translation and independent review

## Dispatch

For a single PDF below 80 physical source pages use the direct workflow. Use the coordinator workflow for multiple PDFs, a PDF of at least 80 pages, or requested independent review. GPT-6.1 Terra high is the suggested coordinator; use Sol or Astra if the user selects it. Use fresh Luna xhigh contexts for translation and review. Start with two translation slots and one review slot. Review ready candidates as they become available and adjust the balance if a queue grows.

Preflight each source once using the frozen Python environment. Start with contiguous ranges of 30–50 source pages for long documents. Adjust to chapters, density, formulas, tables and paragraph breaks. One translator owns each source page. Give neighboring pages as read-only context. Keep cross-page sentences, continued tables, hyphenated words and captions with one translator, then map the resulting text to each original page. A translator receives the source, assigned pages, package inventory and frozen runner. An independent reviewer receives the original, candidate renders, page list and acceptance criteria.

## Handoff

From the document's working folder, substitute actual ranges, paths and the assigned agent identifier:

~~~shell
python recovery/pipeline.py package --state recovery/state.json --pages 31-68 --out work/packages/chapter-2 --owner AGENT_ID
python recovery/pipeline.py status --state recovery/state.json --packages work/packages/chapter-2 --candidate PACKAGE_CANDIDATE.state.json
~~~

The package contains editable state, inventory, manifest and read-only neighboring inventories. The translator keeps the patch in that folder as edits.json, applies it to the package state, then builds and verifies a preview. Package previews cannot be published. The reviewer views the actual pages, returns candidate-bound observations and reports material blockers separately. The coordinator registers unblocked observations with review, even if other pages need repair.

Only the coordinator updates the main state. Pass one manifest per patch in matching order:

~~~shell
python recovery/pipeline.py apply --state recovery/state.json --edits work/packages/chapter-2/edits.json --package work/packages/chapter-2/package.json
python recovery/pipeline.py build --state recovery/state.json
python recovery/pipeline.py verify --state FINAL.state.json --previous-state FIRST_PACKAGE.state.json --previous-state SECOND_PACKAGE.state.json
~~~

Identical committed patch hashes are safe to replay. A stale baseline identifies conflicting source pages. Re-export the affected unfinished range and apply the incremental edits against its current IDs. Shared glossary and issue edits go through the coordinator. Explicit context dependencies must be present and unchanged for preview observations to carry into the final candidate. Final navigation and other document-level checks always run on the full declared scope.

## Progress and recovery

Use status per source with the active package directories and candidate snapshots. It shows pending translation and inventory, saved and applied edits, built/reviewed/published ranges, blockers and the next step. Snapshot review counts refer to those candidates; verify determines eligibility on the final one. Save actual agent identifiers, committed paths and unfinished pages in the handoff. On resume, check the manifest, committed patches, candidate states and active job/PID. Continue with the original agent when possible. If unavailable, dispatch a fresh agent with only the unfinished range and named return items. Use separate folders for new package versions.

Report meaningful stage changes and blockers immediately. During long runs summarize changed progress roughly every 20 minutes, using completion events and disk logs. On Windows use a hidden process launch for background builds. A build's job JSON records the worker PID, stage, page counts and exit status when available; an interrupted process may leave status running, so confirm that PID before retrying. Use the same validated Python environment throughout. For long extraction or rendering compare --workers 1 and --workers 2; the pipeline falls back to one process on Windows when memory is low. Final writing remains single-process.
