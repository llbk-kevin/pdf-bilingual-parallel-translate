# Coordinator workflow

## Confirm and prepare

Read naming.md and show the exact source/output/task-folder names together with the agent work table before prepare. Include stable task name, document/physical pages, translator/reviewer/writer duties, explicit model and effort, fresh-context choice, dependencies and handoff path. An accepted plan confirms the same table; resume it without asking again. Each PDF has one current state writer and independent review coverage. The writer may also translate; avoid relay-only agents.

Use the current session model for coordination. Recommend Luna xhigh, subject to the user's choice, explicitly passing model='gpt-6-luna', reasoning_effort='xhigh', fork_turns='none'. Check availability once with a minimal probe and reuse its result for the same host/account. A missing static model entry is unverified, not proof of unavailability. Record request arguments and obtainable host evidence; missing actual-model metadata is unverified and does not create a new gate. On actual failure or mismatch, save the queue and ask before substituting a model.

Read actual host capacity with scripts/coordination.py --config <CODEX_HOME>/config.toml. If unset on first use or materially limiting this task, ask whether to change a specific value; current slots can run queued work meanwhile. Change only an approved setting, save the checkpoint, remind the user to fully quit/restart Codex, and check tool availability after restart.

After approved renaming and source hash checks:

~~~text
python scripts/pipeline.py prepare --source SOURCE.pdf --state TASK/recovery/state.json --font CHINESE_FONT
~~~

Follow returned actions and artifact paths. View source renders; choose page ownership by prose density, tables, formulas and continued semantics. Keep a cross-page sentence/table with the same owner, providing adjacent pages as read-only context. Specify image-label and bibliography scope: translate reference titles/descriptions, retaining author, journal, standard, URL and year identifiers. Representative previews precede bulk use of a layout.

## Dispatch and merge

Give translators only the entry, practical.md, confirmed source/state and generated materials. Give reviewers the entry, review.md and generated handoff. Neither receives the other's verdict. Keep actual agent IDs, responsibilities, stages and checkpoints in work/coordination.json. Use coordination.py validate-plan for the existing ledger; field details are in [maintenance.md](maintenance.md#coordination-record-contract).

For a divided document:

~~~text
pipeline package --state AUTHOR_STATE --pages RANGE --out TASK/work/packages/NAME --owner TASK_NAME
pipeline import-package --state AUTHOR_STATE --package TASK/work/packages/NAME
~~~

Use each result's generated actions. The translator applies edits and previews in its assigned package, then delivers that directory's current authoring state and short issues. Import checks source/dependencies, assigned pages, original facts and the unchanged main-page baseline, importing only author decisions. Package QC, candidate fields and runtime paths do not enter the main state. Repeated identical imports do not rewrite it. Do not reconstruct patch chains or hand-edit fingerprints.

A conflict returns the affected pages. Export their current main state again and resume the original translator. Shared glossary/issues remain with the writer. Different documents may have different concurrent writers; the same state never has simultaneous writers.

Dispatch ready work dynamically, without fixed agent counts or role quotas. Reviews may start when their candidates are ready while other documents translate. Keep queued tasks when slots are full; use completion events/bounded waits. Prefer original workers for repairs/rechecks; add agents for independent work or unavailable originals. Report cumulative launches separately from current running agents and continuations.

Memory defaults to max(2 GiB, 10% of physical RAM); work/resource-settings.json may override memory_reserve_bytes or explicitly set memory_checks_enabled=false. User task instructions take precedence. Low memory queues new heavy work, not lightweight edits or already-rendered viewing. Local Python worker admission is separate. Read [tool-runtime.md](tool-runtime.md) only for persistent kernels/background jobs.

## Verify, publish and resume

The writer builds the complete declared selection, then verifies its candidate state. Pass generated review_handoff and observations_template to the independent reviewer. Register pass/repair observations through review; save passed pages before repairing others. Use verify --previous-state with the specifically chosen earlier candidate to reuse valid observations. Partial previews cannot publish.

Publish only when the generated action permits it. The accepted PDF goes beside the source; notes and recovery materials remain in the task folder. Ordinary publication checks dependencies and saves an accepted author snapshot for optional rebuilding. It does not require another build.

On restart load recorded paths and IDs, check running jobs, then resume saved work. Do not guess the newest state from timestamps. If skill code changes, the coordinator uses the new pipeline's refreeze --state AUTHOR_STATE --out NEW_RECOVERY_DIR; never edit active frozen scripts. Re-export affected packages. The coordinator diagnoses and fixes skill defects; translators report evidence. Keep old candidates and their observations intact.
