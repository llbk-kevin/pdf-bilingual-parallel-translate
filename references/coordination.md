# Coordinator workflow

## Confirm and prepare

Read naming.md and show the exact source/output/task-folder names, agent work table and optional official-version reminder before prepare. Include stable task name, document/physical pages, translator/reviewer/writer duties, explicit model and effort, fresh-context choice, dependencies and handoff path. An accepted plan confirms the tables; resume it without asking again. Each PDF has one current state writer and independent review coverage. The writer may also translate; avoid relay-only agents.

Use the current session model for coordination. Recommend Luna xhigh, subject to the user's choice, explicitly passing model='gpt-6-luna', reasoning_effort='xhigh', fork_turns='none'. Check availability once with a minimal probe and reuse its result for the same host/account. A missing static model entry is unverified, not proof of unavailability. Record request arguments and obtainable host evidence; missing actual-model metadata is unverified and does not create a new gate. On actual failure or mismatch, save the queue and ask before substituting a model.

Read actual host capacity with scripts/coordination.py --config <CODEX_HOME>/config.toml. If unset on first use or materially limiting this task, ask whether to change a specific value; current slots can run queued work meanwhile. Change only an approved setting, save the checkpoint, remind the user to fully quit/restart Codex, and check tool availability after restart.

After approved renaming and source hash checks:

~~~text
python scripts/pipeline.py prepare --source SOURCE.pdf --state TASK/recovery/state.json --font CHINESE_FONT
~~~

Preparation checks page content streams and nested forms before extracting glyphs. A known token-limit failure gets one retry with a bounded budget for the affected stream. If it still fails, use the reported source page, object path and limit.

Follow returned actions and artifact paths. View source renders; choose page ownership by prose density, tables, formulas and continued semantics. Keep a cross-page sentence/table with the same owner, providing adjacent pages as read-only context. Specify image-label and bibliography scope: translate reference titles/descriptions, retaining author, journal, standard, URL and year identifiers. Representative previews precede bulk use of a layout.

## Dispatch and merge

Give translators only the entry, practical.md, confirmed source/state and generated materials. Give reviewers the entry, review.md and generated handoff. Neither receives the other's verdict. Keep actual agent IDs, responsibilities, stages and checkpoints in work/coordination.json. Use coordination.py validate-plan for the existing ledger; field details are in [maintenance.md](maintenance.md#coordination-record-contract).

For a divided document:

~~~text
pipeline package --state AUTHOR_STATE --pages RANGE --out TASK/work/packages/NAME --owner TASK_NAME
pipeline import-package --state AUTHOR_STATE --package PACKAGE_A --package PACKAGE_B
~~~

Use the generated actions. Translators deliver their current package state and any issues separately. Combine ready packages in one import. The command checks sources, assigned pages, original facts and main-state baselines before validating and saving the combined authoring state once. Conflicts identify the package and affected pages and leave the entire batch unsaved. Repeated identical imports leave the state untouched.

Export conflicted pages from the current main state and resume the original translator. The writer maintains the shared glossary and collects delivery notes separately. Different documents may have different concurrent writers; the same state never has simultaneous writers.

Dispatch ready work dynamically, without fixed agent counts or role quotas. Reviews may start when their candidates are ready while other documents translate. Keep queued tasks when slots are full; use completion events/bounded waits. Prefer original workers for repairs/rechecks; add agents for independent work or unavailable originals. Report cumulative launches separately from current running agents and continuations.

Memory defaults to max(2 GiB, 10% of physical RAM); work/resource-settings.json may override memory_reserve_bytes or explicitly set memory_checks_enabled=false. User task instructions take precedence. Low memory queues new heavy work, not lightweight edits or already-rendered viewing. Local Python worker admission is separate. Read [tool-runtime.md](tool-runtime.md) only for persistent kernels/background jobs.

## Verify, publish and resume

After translator previews, build and verify the full delivery candidate for formal independent page-by-page review. For multiple reviewers, repeat `--review-pages` on verify to assign disjoint physical page ranges covering all pending pages. Give each reviewer their paths and original-to-output page mapping from review_handoff. Run its generated review command to register their files together. After a substantive fix, pass the earlier candidate to verify with `--previous-state` and assign only the pages it still calls for. Partial previews cannot publish.

Publish only when the generated action permits it. Keep delivery remarks in `work/delivery-notes.json` as a list of entries with `description`, `status` (`open`, `resolved` or `retained`), and `note` when retained. Close substantive issues only after the fix is checked. Open issues block publishing. For remarks-only edits, keep the same candidate and review evidence and publish with the amended notes. The accepted PDF goes beside the source. Publication checks dependencies and saves an author snapshot for optional recovery.

On restart load recorded paths and IDs, check running jobs, then resume saved work. Do not guess the newest state from timestamps. If skill code changes, the coordinator uses the new pipeline's refreeze --state AUTHOR_STATE --out NEW_RECOVERY_DIR; never edit active frozen scripts. Re-export affected packages. The coordinator diagnoses and fixes skill defects; translators report evidence. Keep old candidates and their observations intact.
