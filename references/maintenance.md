# Skill maintenance

## Repository and installation

Maintain llbk-kevin/pdf-bilingual-parallel-translate on main. The installed entry is <CODEX_HOME>/skills/pdf-bilingual-parallel-translate. If CC Switch manages it, resolve the link before editing and verify its type, target and updated contents afterwards. Edit an unmanaged directory in place. Report broken links or divergent copies before making changes.

## Validation and publication

Keep SKILL.md and README.md aligned, along with each changed English reference and its .zh-CN.md counterpart. Keep commands, field names and examples equivalent. Use UTF-8 without BOM and check Markdown links and agents/openai.yaml. Run the installed skill-creator validator when available.

Install requirements-dev.txt in a suitable environment and run from the repository:

~~~text
python -m unittest discover -s tests -v
python scripts/pipeline.py --help
python scripts/pdf_tools.py --help
~~~

The suite generates its own PDFs and fonts. Use the relevant regressions for behavior changes. Exercise page geometry and original-pane isolation for coordinate changes, encoded images and masks for resource changes, and evidence reuse and publication paths for pipeline changes. For optional visual fixtures, run tests/generate_layout_samples.py --out <external-dir> --font <permitted-Chinese-font>, adding --face-index for a font collection.

Keep user inputs, translations, renders, recovery files, fonts and credentials outside the repository. Follow AGENTS.md for commit format and normal push to origin/main.

## Implementation constraints

For coordination changes, test the work-plan validator with full/split page ownership, independent review identities, explicit model requests and real-evidence classification, repeated original-worker continuations and lightweight progress during a heavy-work queue. A static model list is not a capability test. Use a small independent trial from the revised entrypoint; keep its confirmation table, dispatch ledger and checkpoints outside the repository. Count unique agent IDs separately from continuations and concurrent activity.

For tool-lifecycle changes, test success/failure/cancel/orphan/PID reuse, bounded log transport and UTF-8 paths. Run repeated synthetic large-state queries and jobs in an isolated parent, recording initial/peak/end memory and post-warmup growth. Validate real host reset by disappearance of the registered PID/start identity; mark unsupported or unverified cleanup explicitly. Keep host process details and task measurements outside the repository.

- Compress non-image streams without re-encoding original images. Audit traverses reachable resources and checks encoded image streams and their display semantics. Review the encoded-stream inventory when changing the pypdf major version.
- Normalize UserUnit in the in-memory PDFium rendering copy. Use the same matrix and pixel origin for both panes.
- Use source drawing traces and translated fontTools outlines for deletion and collision bounds. Disable font timestamp recalculation for repeatable builds.
- Read raw PDF destination arrays to preserve nullable XYZ coordinates. Follow the geometry and interaction contracts in [inplace.md](inplace.md).

Compare the same input when changing batch drawing, PDF serialization or worker count. Record stage wall/CPU time, peak working set, state bytes, object counts and rendered pages. Check pixels, fonts, navigation and shared resources before changing defaults. The build job and pipeline event records supply timing and scope. Use isolated state copies for comparisons; reserve a full-size trial for a separate maintenance run.

For preparation/freezing changes, test cross-drive references, rollback before publishing state, input preservation and new-version package handoff. Exercise coordination event replay and model identity, and preserve valid local-review reuse. Add a focused regression when a concrete failure reveals a gap. Keep task-specific evidence in the task folder.

For behavior changes, inspect related rules, callers and tests and update conflicts at their source. Maintain the current workflow/state contract and remove obsolete adapters and duplicate entry points. Record concrete remaining issues in the local maintenance report.

## Coordination record contract


Run `python scripts/coordination.py validate-plan --plan TASK/work/coordination.json` before dispatch and after assignment changes. It is read-only, returns ok/errors, model checks and a summary; invalid plans exit 1. It validates structure, not user authorization, model availability or semantic quality.

- documents: id, selected physical pages as a positive integer list, and state_writer referencing a translation/repair task. The writer may have owns_edits=false when page translators own the edits.
- tasks: unique id and display name; document; pages; phase (translate/review/repair); explicit owns_edits; model; reasoning_effort; fork_turns; responsibilities (text); handoff; depends_on task IDs; status (queued/running/completed/blocked). Translation and review tasks require fork_turns='none'. Read-only context pages are not editing pages. Translation owners and review tasks must cover the selection; active edit ownership cannot overlap. A repair task reassigns pages only after the previous owner completes or transfers ownership. Review dependencies must transitively include the relevant translators.
- tasks may record agent_id, artifacts, resource_class, estimated_memory_bytes and resume_count (default 0). Increment resume_count when continuing the same agent; do not add another launch for a follow-up.
- launches is append-only: task, unique actual agent_id, requested_model, requested_effort, optional actual_model/actual_effort, host/tool evidence and evidence_agent_id. Failed calls without an agent ID are diagnostics, not launches. No model substitution is allowed; mismatched values or an error block validation. Actual values are verified only when evidence_agent_id matches this launch's agent_id and evidence names its host/tool record. Missing or probe-only evidence is unverified. model_checks stores probe evidence objects with agent_id when created, host/account scope and availability result.

For a short two-page PDF, use one translate task owning pages [1,2] and one review task depending on it, with that translate task as state_writer. For a split document, the writer's translation task can depend on page translators before review becomes ready. A queued/running review also depends on overlapping pending repairs; feedback is an artifact, not a circular dependency from repair back to that same review task. Reviewers submit observations for serial registration by the writer. The same agent cannot translate/repair and independently review its document, including past launch identities. A new reviewer receives source, renders, criteria and an empty template, not the translator's verdict.

On the first recorded launch for each document, record copies the confirmed writer task’s document, id, model and reasoning_effort into that launch’s initial_writer, even if a page translator launches first. Preserve this append-only entry on resume. Validation compares it to the current state_writer. Changing the number of translators does not reselect the lead. Initially confirmed model overrides are valid. Older launches without this field carry no retrospective first-dispatch evidence.

The summary’s staffing_by_document counts translation task rows owning edits, independent review rows and a separate writer only if not counted as a translator. List all ranges for one planned person in one row; repair/continuation tasks do not add planned seats. Read first-wave membership from the confirmed work table.

The summary distinguishes unique created_agents (work and recorded probes), work_agents, probe_agents, currently running work agent IDs, queued/blocked tasks and total resume_count. It is based on recorded identities, never call counts, process counts or UI totals. Do not label cumulative created agents as a concurrency peak.

Each document state has one writer at a time. Different documents can update concurrently. Reviewers submit real observations; the assigned document writer registers them and imports accepted package results. The coordinator owns overall decisions and publication.

Use coordination record --plan TASK/work/coordination.json --event FILE for launch, resume, status and model-evidence events. Each event has a unique id, type and task. A launch supplies agent_id/requested_model/requested_effort; resume supplies the original agent_id; status supplies status and optional artifacts object; model-evidence supplies agent_id and available actual_model/actual_effort/evidence/evidence_agent_id. The coordinator serializes updates. Replaying the same event is a no-op; reusing its id for different content is rejected. Invalid updates leave the ledger unchanged. Save actual host evidence when available, never another agent's probe.
