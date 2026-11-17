# Coordinating translation and independent review

## Dispatch and host setup

Every PDF gets a translation task and an independent review task with a fresh context, including a single short document. The coordinator uses the current session model. Luna xhigh is the suggested translation/review model; explicit user choices and available models take precedence. When using the suggested model, pass model and reasoning_effort explicitly and use fork_turns=none for independent review; record the actual spawn values. Long documents may use additional tasks divided by chapters, coherent passages and workload. Each source page has one current editing owner.

Check actual subagent tools and read host settings with scripts/coordination.py --config <CODEX_HOME>/config.toml. An unset agents.max_concurrent_threads_per_session uses the host default. On first use with no explicit setting, or when capacity affects dispatch, explain the current situation and ask whether the user wants a specific change. Record the choice in work/coordination.json. Existing capacity can run queued work while this optional choice is pending. Write a setting only after approval of its exact value. After a change, save a checkpoint, remind the user to fully quit and restart Codex, and verify actual tool availability after restart. Configured capacity alone does not establish effective capacity.

Follow [naming.md](naming.md) before prepare and dispatch. Give workers confirmed paths, the frozen command_prefix/runner, page ownership and compact inventory. Adjacent pages provide read-only context. Assign cross-page sentences and continued tables together, then place each part on its original page.

## Dynamic scheduling

Dispatch executable tasks using available slots and memory, with no fixed translation/review allocation. A review becomes ready when its candidate passes machine checks. Other PDFs can keep translating. If slots or memory are insufficient, save the queue and wait for completion or availability changes. Complete the session cleanup below before considering an idle worker released. Use bounded waits; attempt another spawn after availability changes. User-requested phase ordering takes precedence.

Store task ID, document, page range, phase (translate/review), status (queued/running/completed/blocked), depends_on, actual agent ID and artifact paths in work/coordination.json. The helper ready_tasks(tasks, available_slots, memory=None, reserve_bytes=None) selects dependency-ready tasks, preferring available reviews without reserving slots. Its system reserve defaults to max(2 GiB, 20% of physical RAM); the task's work/resource-settings.json can override memory_reserve_bytes. Pass that override to ready_tasks. Each task may provide estimated_memory_bytes (default 256 MiB until measured); record observed usage to improve subsequent estimates. The host tools perform spawning and waiting. A reviewer receives source pages, candidate renders, acceptance criteria and a blank observations template in a fresh context.

Each document state has one writer at a time. Different documents can update concurrently. Reviewers submit real observations; the assigned document writer registers them and merges accepted patches. The coordinator owns overall decisions and publication.

## Packages and recovery

Export coherent ranges with pipeline package --state recovery/state.json --pages RANGE --out work/packages/PACKAGE --owner AGENT_ID. Each package contains editable state, compact inventory, a baseline and read-only adjacent context. Workers save edits.json, apply and preview locally. The document writer applies the patch with its package manifest. Replayed patch fingerprints are idempotent; baseline conflicts return only affected pages.

Use status with active packages and candidate states for progress. Keep actual agent IDs, committed paths, unfinished pages and blockers on disk. Resume an available original worker or give a new worker the remaining assignment from this checkpoint. Review reuse requires matching page evidence and dependencies.

Use verify's review_handoff and observations_template. Save clear-page observations before repairing a blocker, then use --previous-state for valid evidence. Report meaningful stage changes and blockers. Use source plus saved state for builds and keep all artifacts in the source-stem folder.

Local extraction/rendering uses --workers auto or a positive integer. Machine-wide CPU/memory leases coordinate concurrent PDF jobs. Worker count and selection reasons appear in resource telemetry. Final PDF writing has one writer.

## Tool-session ownership and cleanup

Run scripts/coordination.py memory --task-dir TASK before a new batch of heavy tasks. Check again at stage changes or after a resource failure, not by continuous polling. Low memory queues new heavy work while existing jobs finish. Worker admission failures include available, reserved, estimated and coordinator RSS bytes; read those facts before retrying.

From the worker's own Node kernel, directly launch the frozen Python executable with scripts/coordination.py session-register --task-dir TASK --agent ACTUAL_ID. It verifies kernel.js and its session ID in the caller's parent chain, and saves PID, process start time, agent and memory under work/tool-sessions/. An unverifiable caller is reported, not guessed.

Before handing off: save edits, observations and a restart checkpoint inside the task; ensure every live child job is registered with task_runtime; call session-mark --record RECORD --status cleanup_required --checkpoint FILE; then invoke that worker's own js_reset tool when available. Do not immediately restart Node just to announce completion. Resume from disk in a new kernel. If reset is unavailable, mark cleanup_unavailable and report it. Use a supported host close-agent operation only if one actually exists.

The coordinator runs sessions --task-dir TASK to observe whether the recorded PID/start identity disappeared; only a previously cleanup_required session becomes reset_observed. Completed, interrupted or closed agent labels alone are not cleanup evidence. Unknown kernels are listed separately and are never terminated by name, size or a guessed working directory. Confirm no unsupervised job remains before resetting a kernel; use task_runtime cancel only for its verified job tree. A whole-app restart is a last resort when the host cannot release a known idle session.
